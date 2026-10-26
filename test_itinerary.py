
from models import TripRequest
from itinerary import generate_itinerary
from agents.destination_agent import DestinationAgent


def make_trip(**overrides):
    data = {
        "origin": "Xi'an",
        "destination": "Chengdu",
        "days": 5,
        "budget": 3000,
        "travelers": 2,
        "interests": ["nature", "food", "culture"],
    }
    data.update(overrides)
    return TripRequest(**data)


def generate_for_test(trip):
    agent = DestinationAgent()
    selected = agent.run(trip.destination, trip.interests)
    return generate_itinerary(trip, selected)

def test_budget_calculation_is_consistent():
    result = generate_itinerary(make_trip())

    budget = result["budget"]

    expected_total = (
        budget["estimated_food"]
        + budget["estimated_local_transport"]
        + budget["estimated_accommodation"]
        + budget["estimated_attraction_entries"]
    )

    assert budget["estimated_total"] == expected_total
    assert budget["remaining_budget"] == round(
        budget["user_budget"] - expected_total, 2
    )
    assert budget["within_budget"] == (
        expected_total <= budget["user_budget"]
    )


def test_unsupported_destination_is_reported():
    result = generate_itinerary(
        make_trip(destination="Beijing")
    )

    assert result["status"] == "unsupported_destination"
    assert "Chengdu" in result["supported_destinations"]


def test_itinerary_contains_requested_number_of_days():
    result = generate_itinerary(make_trip(days=3))

    assert result["status"] == "success"
    assert len(result["itinerary"]) == 3
    assert [day["day"] for day in result["itinerary"]] == [1, 2, 3]


def test_daily_activity_hours_never_exceed_limit():
    result = generate_itinerary(
        make_trip(days=1, interests=["nature"])
    )

    for day in result["itinerary"]:
        assert day["planned_activity_hours"] <= 8


def test_unassigned_attractions_are_reported():
    result = generate_itinerary(
        make_trip(days=1, interests=["nature"])
    )

    # Panda Base takes 4 hours and Mount Qingcheng takes 5.
    # Both cannot fit into one 8-hour day.
    assert len(result["unassigned_attractions"]) >= 1


def test_invalid_trip_duration_is_rejected():
    try:
        make_trip(days=0)
    except ValueError:
        pass
    else:
        raise AssertionError("A zero-day trip should be rejected")
