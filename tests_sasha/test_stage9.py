import unittest
from pathlib import Path
from providers.config import RESOURCE_ROOT
from copy import deepcopy

from providers.official_sources.client import load_registry, fetch_official
from providers.official_sources.extract import extract_published_claims, enrich_from_official_claims
from workflows.official_verification import run_stage9

ROOT = Path(__file__).resolve().parent.parent
SOURCES = load_registry()


def demo_file(name):
    return (RESOURCE_ROOT / 'fixtures' / name).read_text(encoding='utf-8')


class FakeResponse:
    def __init__(self, body, content_type='text/plain', status_code=200):
        self.body = body.encode('utf-8')
        self.status_code = status_code
        self.headers = {'Content-Type': content_type}
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError('HTTP error')
    def iter_content(self, chunk_size=8192):
        yield self.body
    def close(self):
        pass


class Stage9Tests(unittest.TestCase):
    def test_registry_contains_reviewed_https_urls(self):
        self.assertEqual(len(SOURCES), 3)
        self.assertTrue(all(v['url'].startswith('https://') for v in SOURCES.values()))

    def test_bmy_seasonal_hours_from_synthetic_html(self):
        claims = extract_published_claims(SOURCES['bmy-guide'], demo_file('bmy_guide_demo.html'),
                                          mode='synthetic_fixture', travel_date='2026-11-10')
        self.assertIn('08:30-17:00', claims['fields']['opening_hours'])
        self.assertIn('08:30-16:30', claims['fields']['opening_hours'])
        self.assertFalse(claims['claims_are_live'])

    def test_bmy_adult_ticket_not_student(self):
        claims = extract_published_claims(SOURCES['bmy-tickets'], demo_file('bmy_tickets_demo.html'),
                                          mode='synthetic_fixture')
        self.assertEqual(claims['fields']['ticket_price_cny'], 120)
        self.assertTrue(claims['fields']['booking_required'])

    def test_sxhm_date_range_rejected(self):
        html = demo_file('sxhm_2026_demo.html')
        valid = extract_published_claims(SOURCES['sxhm-extended-2026'], html,
                                         mode='synthetic_fixture', travel_date='2026-11-12')
        invalid = extract_published_claims(SOURCES['sxhm-extended-2026'], html,
                                           mode='synthetic_fixture', travel_date='2026-11-18')
        self.assertIn('opening_hours', valid['fields'])
        self.assertEqual(invalid['fields'], {})

    def test_unmatched_source_is_not_treated_as_evidence(self):
        bad = extract_published_claims(SOURCES['bmy-tickets'], '<p>Some other business 普通成人票120元</p>',
                                       mode='live_official')
        self.assertEqual(bad['fields'], {})

    def test_fixture_must_never_enrich(self):
        claims = extract_published_claims(SOURCES['bmy-tickets'], demo_file('bmy_tickets_demo.html'),
                                          mode='synthetic_fixture')
        item = {'name_zh': '秦始皇帝陵博物院', 'city_zh': '西安市', 'ticket_price_cny': None}
        out = enrich_from_official_claims({'places': [item]}, claims)
        self.assertIsNone(out['places'][0]['ticket_price_cny'])
        self.assertEqual(out['official_verification']['status'], 'synthetic_not_applied')

    def test_live_claims_fill_correct_record_only(self):
        claims = extract_published_claims(SOURCES['bmy-tickets'], demo_file('bmy_tickets_demo.html'),
                                          mode='live_official', now='2026-11-04T08:00:00+00:00')
        items = [{'name_zh': '秦始皇帝陵博物院', 'city_zh': '西安市', 'ticket_price_cny': None},
                 {'name_zh': '秦始皇帝陵博物院停车场', 'city_zh': '西安市', 'ticket_price_cny': None}]
        before = deepcopy(items)
        out = enrich_from_official_claims({'places': items}, claims)
        self.assertEqual(out['places'][0]['ticket_price_cny'], 120)
        self.assertEqual(out['places'][0]['estimated_cost_cny'], 120)
        self.assertIsNone(out['places'][1]['ticket_price_cny'])
        self.assertEqual(items, before)

    def test_robots_disallow_skips_page(self):
        calls = []
        def fake_get(url, **kwargs):
            calls.append(url)
            return FakeResponse('User-agent: *\nDisallow: /guide/', 'text/plain')
        res = fetch_official('bmy-guide', http_get=fake_get)
        self.assertEqual(res['status'], 'robots_disallow')
        self.assertEqual(res['http_attempts'], 1)
        self.assertEqual(len(calls), 1)

    def test_robots_allow_one_page(self):
        calls = []
        def fake_get(url, **kwargs):
            calls.append(url)
            if url.endswith('/robots.txt'):
                return FakeResponse('User-agent: *\nAllow: /', 'text/plain')
            return FakeResponse(demo_file('bmy_guide_demo.html'), 'text/html; charset=utf-8')
        result = fetch_official('bmy-guide', http_get=fake_get)
        self.assertEqual(result['http_attempts'], 2)
        self.assertEqual(result['status'], 'fetched')
        self.assertEqual(len(calls), 2)

    def test_invalid_source_never_requests(self):
        def bomb(*a, **k):
            raise AssertionError('network called')
        with self.assertRaises(ValueError):
            fetch_official('typo', http_get=bomb)

    def test_stage9_offline_sample_is_zero_cost(self):
        result = run_stage9(text="I love history in Xi'an", city='西安市',
                            keyword='秦始皇帝陵博物院', category='museum', limit=8,
                            source_id='bmy-guide', sample=True, view='handoff')
        self.assertEqual(result['usage']['official_website_http_attempts'], 0)
        self.assertEqual(result['usage']['amap_v5_requests_attempted'], 0)
        self.assertEqual(result['usage']['llm_tokens'], 0)
        self.assertEqual(result['official_verification']['fields_added'], 0)

    def test_date_validated_before_provider(self):
        def no_provider(*a, **k):
            raise AssertionError('provider should never be called')
        with self.assertRaises(ValueError):
            run_stage9(text='x', city='西安市', keyword=None, date='bad-date',
                       provider_runner=no_provider)

    def test_unsupported_source_rejected_before_provider(self):
        def no_provider(*a, **k):
            raise AssertionError('provider should never be called')
        with self.assertRaises(ValueError):
            run_stage9(text='x', city='西安市', keyword='a', source_id='unknown',
                       sample=True, provider_runner=no_provider)


if __name__ == '__main__':
    unittest.main()
