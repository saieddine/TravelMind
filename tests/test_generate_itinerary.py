import pytest

from agents.itinerary_agent import ItineraryAgent
from models.attraction import AttractionInput
from models.budget import BudgetAssumptions
from models.itinerary import ItineraryPlan


# Create sample attractions for itinerary generation tests
def create_attraction(
    attraction_id: str,
    name: str,
    duration: int | None,
    cost: float | None
):
    return AttractionInput(
        id=attraction_id,
        name_en=name,
        name_zh="测试景点",
        city_zh="西安市",
        category="Culture",
        verification_status="curated_sample",
        duration_minutes=duration,
        duration_status="estimated" if duration is not None else "unknown",
        ticket_price_cny=cost,
        estimated_cost_cny=cost,
        cost_status="estimated" if cost is not None else "unknown",
        selection_reason="Selected for itinerary testing."
    )


# Create an agent with complete budget assumptions
def create_test_agent():
    assumptions = BudgetAssumptions(
        accommodation_per_room_per_night_cny=300,
        meals_per_person_per_day_cny=80,
        local_transport_per_person_per_day_cny=30,
        people_per_room=2
    )

    return ItineraryAgent(budget_assumptions=assumptions)


# Test that the agent returns a complete itinerary structure
def test_generates_complete_itinerary():
    agent = create_test_agent()

    attractions = [
        create_attraction("A1", "Museum", 120, 50),
        create_attraction("A2", "Park", 90, 0)
    ]

    plan = agent.generate_itinerary(
        destination="Xi'an",
        attractions=attractions,
        travelers=2,
        days=2
    )

    assert isinstance(plan, ItineraryPlan)
    assert plan.destination == "Xi'an"
    assert len(plan.days) == 2
    assert len(plan.days[0].activities) == 2
    assert plan.unassigned_attractions == []


# Test that only scheduled attractions contribute to the budget
def test_budget_uses_only_scheduled_attractions():
    agent = create_test_agent()

    attractions = [
        create_attraction("A1", "Museum", 120, 50),
        create_attraction("A2", "Full-day attraction", 420, 100)
    ]

    plan = agent.generate_itinerary(
        destination="Xi'an",
        attractions=attractions,
        travelers=2,
        days=1
    )

    # Only the scheduled museum contributes to attraction costs
    assert plan.budget.estimated_attraction_entries == 100
    assert len(plan.unassigned_attractions) == 1


# Test that unknown attraction durations are reported
def test_reports_attractions_with_unknown_duration():
    agent = create_test_agent()

    attractions = [
        create_attraction("A1", "Museum", None, 50)
    ]

    plan = agent.generate_itinerary(
        destination="Xi'an",
        attractions=attractions,
        travelers=2,
        days=2
    )

    assert len(plan.unassigned_attractions) == 1
    assert plan.unassigned_attractions[0].attraction_id == "A1"
    assert plan.budget.estimated_attraction_entries == 0


# Test that unknown costs produce an incomplete budget warning
def test_reports_unknown_budget_costs():
    agent = create_test_agent()

    attractions = [
        create_attraction("A1", "Museum", 120, None)
    ]

    plan = agent.generate_itinerary(
        destination="Xi'an",
        attractions=attractions,
        travelers=2,
        days=2
    )

    assert plan.budget.estimated_attraction_entries is None
    assert plan.budget.estimated_total is None
    assert any("budget is unavailable" in warning for warning in plan.warnings)


# Test that an empty destination is rejected
def test_rejects_empty_destination():
    agent = create_test_agent()

    with pytest.raises(ValueError):
        agent.generate_itinerary(
            destination=" ",
            attractions=[],
            travelers=2,
            days=2
        )


# Test that an invalid trip duration is rejected
def test_rejects_invalid_trip_duration():
    agent = create_test_agent()

    with pytest.raises(ValueError):
        agent.generate_itinerary(
            destination="Xi'an",
            attractions=[],
            travelers=2,
            days=0
        )


# Test that an invalid traveler count is rejected
def test_rejects_invalid_traveler_count():
    agent = create_test_agent()

    with pytest.raises(ValueError):
        agent.generate_itinerary(
            destination="Xi'an",
            attractions=[],
            travelers=0,
            days=2
        )
