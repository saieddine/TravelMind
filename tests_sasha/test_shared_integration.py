import unittest
from copy import deepcopy
from unittest.mock import patch, Mock
from agents.destination_agent import DestinationAgent
from models import TripRequest
from orchestrator import TravelMindOrchestrator
from integration.itinerary_adapter import to_itinerary_places, to_legacy_itinerary_places


def trip(destination="Xi'an"):
    return TripRequest(origin="Beijing", destination=destination, days=2, budget=3000,
                       travelers=2, interests=["museum"])

class SharedIntegrationTests(unittest.TestCase):
    def test_authoritative_request_and_coordinator_collection(self):
        request = trip()
        with patch("requests.get", side_effect=AssertionError("No network")), \
             patch("requests.post", side_effect=AssertionError("No network")):
            result = TravelMindOrchestrator().collect_agent_results(request, scenario="rain")
        TripRequest.model_validate(result["trip"])
        self.assertTrue(result["destination"]["places"])
        self.assertEqual(result["selection_scope"], "candidates_only")
        self.assertEqual(result["context"]["context"]["weather"]["status"], "simulated_scenario")
        self.assertEqual(result["usage"]["external_requests_attempted"], 0)
        self.assertEqual(request, trip())

    def test_main_coordinator_behavior_is_preserved(self):
        result = TravelMindOrchestrator().plan_trip(trip("Chengdu"))
        self.assertEqual(result["result"]["status"], "success")
        self.assertEqual(TravelMindOrchestrator().plan_trip(trip())["result"]["status"], "unsupported_destination")

    def test_context_collection_does_not_allow_conflicting_llm_city(self):
        with self.assertRaises(ValueError):
            TravelMindOrchestrator().collect_agent_results(trip(), interpreted_intent={
                "city": "Beijing", "interests": [], "category": None})

    def test_null_cost_and_provenance_preserved(self):
        original = DestinationAgent().run_candidates("Museums in Xi'an")["places"]
        snapshot = deepcopy(original)
        converted = to_itinerary_places(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(converted[0]["id"], original[0]["attraction_id"])
        self.assertEqual(converted[0]["source"], original[0]["source"])
        self.assertIsNone(converted[0]["estimated_cost_cny"])
        self.assertEqual(converted[0]["cost_status"], "unknown")
        with self.assertRaises(ValueError):
            to_legacy_itinerary_places(original)

    def test_known_cost_is_per_person_and_zero_is_preserved(self):
        p = {"attraction_id": "fixture", "name_en": "Fixture", "duration_minutes": 90,
             "duration_status": "estimated", "estimated_cost_cny": 0, "cost_status": "estimated"}
        result = to_legacy_itinerary_places([p])[0]
        self.assertEqual(result["duration_hours"], 1.5)
        self.assertEqual(result["entry_cost"], 0)
        self.assertEqual(result["cost_basis"], "per_person")
        with self.assertRaises(ValueError):
            to_itinerary_places([{**p, "cost_basis": "group"}])

    def test_invalid_numeric_values_rejected(self):
        for duration,cost in ((-1,0),(60,True),(60,float("nan")),(1.5,0)):
            with self.subTest(duration=duration,cost=cost), self.assertRaises(ValueError):
                to_itinerary_places([{"duration_minutes":duration,"estimated_cost_cny":cost}])

    def test_unknown_status_is_not_promoted_to_estimate(self):
        place = {"duration_minutes": 60, "duration_status": "unknown",
                 "estimated_cost_cny": 10, "cost_status": "unknown"}
        result = to_itinerary_places([place])[0]
        self.assertEqual(result["duration_status"], "unknown")
        self.assertEqual(result["cost_status"], "unknown")
        self.assertIsNone(result["duration_minutes"])
        self.assertIsNone(result["estimated_cost_cny"])
        with self.assertRaises(ValueError):
            to_legacy_itinerary_places([place])

    def test_coordinate_reference_system_is_preserved(self):
        place = {"location": {"latitude": 34.2, "longitude": 108.9}, "coordinate_system": "GCJ-02"}
        converted = to_itinerary_places([place])[0]
        self.assertEqual(converted["coordinates"]["system"], "GCJ-02")
        self.assertNotIn("coordinates", place)

    def test_supplied_authoritative_model_is_used(self):
        model = Mock()
        to_itinerary_places([{"attraction_id": "fixture"}], attraction_model=model)
        model.model_validate.assert_called_once()
        self.assertEqual(model.model_validate.call_args.args[0]["id"], "fixture")
