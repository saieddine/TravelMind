import unittest
from pathlib import Path
from unittest.mock import patch


from providers.amap.poi_v5 import AmapV5Client, amap_poi_to_place, gcj02
from providers.baidu.places import BaiduPlacesClient
from data.provider_router import run_provider_search, add_contract_fields


class FakeResponse:
    def __init__(self, obj):
        self.obj = obj
    def raise_for_status(self):
        return None
    def json(self):
        return self.obj


class CallCounter:
    def __init__(self, obj):
        self.obj = obj
        self.calls = []
    def __call__(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse(self.obj)


AMAP_SAMPLE = {'status': '1', 'info': 'OK', 'pois': [
    {'id': 'A001', 'name': '测试博物馆', 'cityname': '西安市', 'adname': '雁塔区',
     'address': '测试路1号', 'location': '108.95,34.25',
     'type': '科教文化服务;博物馆',
     'business': {'opentime_today': '09:00-17:00', 'opentime_week': '周二至周日 09:00-17:00',
                  'cost': '45.0', 'rating': '4.5'}}
]}
BAIDU_SAMPLE = {'status': 0, 'results': [
    {'uid': 'B1', 'name': '测试博物馆', 'city': '西安市', 'address': '测试路1号',
     'location': {'lat': 34.25, 'lng': 108.95},
     'detail_info': {'shop_hours': '09:00-17:00', 'price': '38',
                     'overall_rating': '4.6'}}
]}


class ProviderTests(unittest.TestCase):
    @patch('providers.amap.poi_v5.requests.get', side_effect=AssertionError('NO NETWORK'))
    @patch('providers.baidu.places.requests.get', side_effect=AssertionError('NO NETWORK'))
    @patch('agents.destination_agent.ai_interpret_request', side_effect=AssertionError('NO LLM'))
    def test_offline_zero_calls_and_tokens(self, *_mocks):
        result = run_provider_search("Xi'an history and museums")
        self.assertEqual(result['mode'], 'offline_demo')
        self.assertEqual(result['usage']['amap_v5_requests_attempted'], 0)
        self.assertEqual(result['usage']['baidu_v3_requests_attempted'], 0)
        self.assertEqual(result['usage']['llm_tokens'], 0)
        self.assertGreater(len(result['places']), 0)

    def test_amap_v5_params_and_one_call(self):
        call = CallCounter(AMAP_SAMPLE)
        client = AmapV5Client(key='TEST', http_get=call)
        records = client.search(city='西安市', keyword='测试博物馆', category='museum', limit=3)
        self.assertEqual(len(call.calls), 1)
        url, params, timeout = call.calls[0]
        self.assertEqual(url, 'https://restapi.amap.com/v5/place/text')
        self.assertEqual(params['show_fields'], 'business')
        self.assertEqual(params['region'], '西安市')
        self.assertEqual(params['city_limit'], 'true')
        self.assertEqual(params['page_size'], 3)
        self.assertEqual(records[0]['opening_hours'], '周二至周日 09:00-17:00')
        self.assertEqual(records[0]['opening_hours_today'], '09:00-17:00')
        self.assertEqual(records[0]['ticket_price_cny'], None)
        self.assertEqual(records[0]['average_spend_raw'], '45.0')
        self.assertEqual(records[0]['coordinates']['system'], 'GCJ-02')

    def test_amap_missing_optional_fields_stay_null(self):
        raw = {'id': 'A2', 'name': 'No hours', 'address': [], 'location': [],
               'business': [], 'cityname': '西安市'}
        p = amap_poi_to_place(raw, '西安市', '2026-11-03T00:00:00+00:00')
        self.assertIsNone(p['opening_hours'])
        self.assertIsNone(p['coordinates'])
        self.assertIsNone(p['ticket_price_cny'])
        self.assertIsNone(gcj02('not a coordinate'))

    def test_baidu_v3_params_and_one_call(self):
        call = CallCounter(BAIDU_SAMPLE)
        client = BaiduPlacesClient(key='TEST', http_get=call)
        records = client.search_named(city='西安市', keyword='测试博物馆')
        self.assertEqual(len(call.calls), 1)
        url, params, _ = call.calls[0]
        self.assertTrue(url.endswith('/place/v3/region'))
        self.assertEqual(params['scope'], 2)
        self.assertEqual(params['ret_coordtype'], 'gcj02ll')
        self.assertEqual(records[0]['provider_price_raw'], '38')
        self.assertIsNone(records[0]['ticket_price_cny'])

    def test_no_baidu_if_amap_has_hours(self):
        a = AmapV5Client(key='TEST', http_get=CallCounter(AMAP_SAMPLE))
        class Never:
            def search_named(self, **kwargs):
                raise AssertionError('No Baidu request allowed')
        result = run_provider_search('Visit Xi\'an', keyword='测试博物馆', category='museum',
                                     live_amap=True, with_baidu=True,
                                     amap_client=a, baidu_client=Never())
        self.assertEqual(result['usage']['amap_v5_requests_attempted'], 1)
        self.assertEqual(result['usage']['baidu_v3_requests_attempted'], 0)

    def test_baidu_replaces_one_complete_provider_record(self):
        amap = {'status': '1', 'pois': [{
            'id': 'A3', 'name': '测试博物馆', 'cityname': '西安市',
            'address': 'Amap Address', 'location': '108.9,34.2',
            'business': {'cost': '50'}
        }]}
        a_call = CallCounter(amap)
        b_call = CallCounter(BAIDU_SAMPLE)
        result = run_provider_search('Visit Xi\'an', keyword='测试博物馆',
                                     live_amap=True, with_baidu=True,
                                     amap_client=AmapV5Client(key='TEST', http_get=a_call),
                                     baidu_client=BaiduPlacesClient(key='TEST', http_get=b_call))
        p = result['places'][0]
        self.assertEqual(len(a_call.calls), 1)
        self.assertEqual(len(b_call.calls), 1)
        self.assertEqual(p['opening_hours'], '09:00-17:00')
        self.assertEqual(p['address_zh'], '测试路1号')
        self.assertEqual(p['source']['provider'], 'baidu_maps')
        self.assertIsNone(p['ticket_price_cny'])
        self.assertIsNone(p['estimated_cost_cny'])
        self.assertEqual(p['provider_price_raw'], '38')
        self.assertNotIn('average_spend_raw', p)
        self.assertEqual(result['usage']['baidu_v3_requests_attempted'], 1)

    def test_different_name_never_merged(self):
        b = {'status': 0, 'results': [{'uid': 'B3', 'name': '无关餐厅', 'city': '西安市',
                                     'detail_info': {'shop_hours': '24小时'}}]}
        a = {'status': '1', 'pois': [{'name': '测试博物馆', 'id': 'A4',
                                    'cityname': '西安市', 'business': {}}]}
        result = run_provider_search('Visit Xi\'an', keyword='测试博物馆',
                                     live_amap=True, with_baidu=True,
                                     amap_client=AmapV5Client(key='TEST', http_get=CallCounter(a)),
                                     baidu_client=BaiduPlacesClient(key='TEST', http_get=CallCounter(b)))
        self.assertIsNone(result['places'][0]['opening_hours'])
        self.assertTrue(any('no exact' in w for w in result['warnings']))

    def test_validates_before_all_calls(self):
        class Never:
            def search(self, **kwargs):
                raise AssertionError('should not call Amap')
        with self.assertRaises(ValueError):
            run_provider_search('Xi\'an', live_amap=True, with_baidu=True,
                                amap_client=Never(), keyword=None)
        with self.assertRaises(ValueError):
            run_provider_search('Xi\'an', live_amap=True, travel_date='2026-02-31',
                                amap_client=Never())

    def test_curated_ticket_price_per_person_not_unknown_zero(self):
        result = run_provider_search('history and museums in Xi\'an', limit=5)
        a = next(p for p in result['places'] if p['name_zh'] == '秦始皇帝陵博物院')
        self.assertEqual(a['estimated_cost_cny'], 120)
        self.assertEqual(a['cost_basis'], 'per_person')
        b = add_contract_fields({'ticket_price_cny': None})
        self.assertIsNone(b['estimated_cost_cny'])
        self.assertEqual(b['cost_status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
