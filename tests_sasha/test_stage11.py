import unittest
from unittest.mock import Mock
from workflows.routes import build_route, parse_point
from providers.routing.amap import AmapRoutingClient, parse_route

O = (108.94786, 34.334885)
D = (108.97076, 34.319389)


class Stage11Tests(unittest.TestCase):
    def test_default_zero_requests(self):
        result = build_route(origin=O, destination=D)
        self.assertEqual(result['mode'], 'offline_synthetic')
        self.assertEqual(result['usage']['amap_routing_requests_attempted'], 0)
        self.assertEqual(result['usage']['llm_tokens'], 0)
        self.assertEqual(result['route']['status'], 'simulated_not_verified')

    def test_valid_mocked_live_walking_one_request(self):
        response = Mock()
        response.json.return_value = {'status': '1', 'route': {'paths': [
            {'distance': '2413', 'cost': {'duration': '2099'}}]}}
        http_get = Mock(return_value=response)
        client = AmapRoutingClient(api_key='not-real-testing-key', http_get=http_get)
        result = build_route(origin=O, destination=D, live=True, client=client)
        self.assertEqual(http_get.call_count, 1)
        self.assertEqual(http_get.call_args.args[0], 'https://restapi.amap.com/v5/direction/walking')
        self.assertEqual(http_get.call_args.kwargs['params']['show_fields'], 'cost')
        self.assertEqual(http_get.call_args.kwargs['params']['origin'], '108.947860,34.334885')
        self.assertEqual(result['route']['duration_minutes'], 35)
        self.assertEqual(result['route']['distance_m'], 2413)
        self.assertEqual(result['usage']['amap_routing_requests_attempted'], 1)

    def test_driving_mode_single_request(self):
        response = Mock()
        response.json.return_value = {'status': '1', 'route': {'paths': [
            {'distance': '3500', 'cost': {'duration': '580'}}]}}
        http_get = Mock(return_value=response)
        client = AmapRoutingClient(api_key='test-key', http_get=http_get)
        result = build_route(origin=O, destination=D, mode='driving', live=True, client=client)
        self.assertEqual(http_get.call_count, 1)
        self.assertEqual(http_get.call_args.kwargs['params']['strategy'], 32)
        self.assertEqual(result['route']['duration_minutes'], 10)

    def test_missing_duration_remains_null(self):
        data = {'status': '1', 'route': {'paths': [{'distance': '1000'}]}}
        self.assertIsNone(parse_route(data, 'walking')['duration_minutes'])

    def test_no_paths_null(self):
        data = {'status': '1', 'route': {'paths': []}}
        self.assertEqual(parse_route(data, 'walking')['status'], 'no_route')

    def test_error_status_no_retry(self):
        response = Mock()
        response.json.return_value = {'status': '0', 'info': 'INVALID_USER_KEY', 'infocode': '10001'}
        http_get = Mock(return_value=response)
        client = AmapRoutingClient(api_key='test-key', http_get=http_get)
        with self.assertRaises(RuntimeError):
            build_route(origin=O, destination=D, live=True, client=client)
        self.assertEqual(http_get.call_count, 1)

    def test_reject_invalid_coordinates_before_call(self):
        http_get = Mock(side_effect=AssertionError('network was called'))
        client = AmapRoutingClient(api_key='test-key', http_get=http_get)
        with self.assertRaises(ValueError):
            build_route(origin=(34.33, 108.94), destination=D, live=True, client=client)
        http_get.assert_not_called()

    def test_reject_identical_coordinates_before_call(self):
        http_get = Mock(side_effect=AssertionError('network was called'))
        client = AmapRoutingClient(api_key='test-key', http_get=http_get)
        with self.assertRaises(ValueError):
            build_route(origin=O, destination=O, live=True, client=client)
        http_get.assert_not_called()

    def test_parse_coordinate_cli(self):
        self.assertEqual(parse_point('108.94786,34.334885'), O)
        with self.assertRaises(ValueError):
            parse_point('not-a-point')

    def test_missing_key_does_not_call(self):
        client = AmapRoutingClient(api_key='', http_get=Mock(side_effect=AssertionError('network')))
        # With environment key, missing explicit key may load key; enforce missing explicitly.
        client._api_key = None
        with self.assertRaises(ValueError):
            client.plan_route(origin=O, destination=D)

if __name__ == '__main__':
    unittest.main()
