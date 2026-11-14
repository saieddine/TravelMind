
import pytest

from agents.itinerary_agent import ItineraryAgent
from models.attraction import AttractionInput
from models.budget import BudgetAssumptions


# Create a sample attraction with a configurable ticket cost
def create_attraction(attraction_id: str, cost: float | None):
    return AttractionInput(
        id=attraction_id,
        name_en=f"Attraction {attraction_id}",
        name_zh="测试景点",
        city_zh="西安市",
        category="Culture",
        verification_status="curated_sample",
        duration_minutes=120,
        duration_status="estimated",
        ticket_price_cny=cost,
        estimated_cost_cny=cost,
        cost_status="estimated" if cost is not None else "unknown",
        selection_reason="Selected for budget testing."
    )


# Test that all expense categories are calculated correctly for a group
def test_calculates_complete_group_budget():
    assumptions = BudgetAssumptions(
        accommodation_per_room_per_night_cny=300,
        meals_per_person_per_day_cny=80,
        local_transport_per_person_per_day_cny=30,
        people_per_room=2
    )

    agent = ItineraryAgent(budget_assumptions=assumptions)

    attractions = [
        create_attraction("A1", 50),
        create_attraction("A2", 100)
    ]

    budget = agent.calculate_budget(
        attractions=attractions,
        travelers=2,
        days=3
    )

    # Two travelers share one room for two nights
    assert budget.estimated_accommodation == 600

    # Calculate meals for two travelers over three days
    assert budget.estimated_food == 480

    # Calculate local transportation for the group
    assert budget.estimated_local_transport == 180

    # Calculate attraction costs for both travelers
    assert budget.estimated_attraction_entries == 300

    # Verify the complete group total
    assert budget.estimated_total == 1560


# Test that the required number of rooms is calculated automatically
def test_calculates_required_rooms():
    assumptions = BudgetAssumptions(
        accommodation_per_room_per_night_cny=200,
        people_per_room=2
    )

    agent = ItineraryAgent(budget_assumptions=assumptions)

    budget = agent.calculate_budget(
        attractions=[],
        travelers=5,
        days=3
    )

    # Five travelers need three rooms for two nights
    assert budget.estimated_accommodation == 1200


# Test that an explicitly provided room count is respected
def test_uses_explicit_room_count():
    assumptions = BudgetAssumptions(
        accommodation_per_room_per_night_cny=200
    )

    agent = ItineraryAgent(budget_assumptions=assumptions)

    budget = agent.calculate_budget(
        attractions=[],
        travelers=4,
        days=3,
        rooms=4
    )

    # Four rooms are charged for two nights
    assert budget.estimated_accommodation == 1600


# Test that an unknown attraction cost is not treated as free
def test_unknown_attraction_cost_produces_unknown_total():
    assumptions = BudgetAssumptions(
        accommodation_per_room_per_night_cny=200,
        meals_per_person_per_day_cny=50,
        local_transport_per_person_per_day_cny=20
    )

    agent = ItineraryAgent(budget_assumptions=assumptions)

    attractions = [
        create_attraction("A1", 50),
        create_attraction("A2", None)
    ]

    budget = agent.calculate_budget(
        attractions=attractions,
        travelers=2,
        days=2
    )

    assert budget.estimated_attraction_entries is None
    assert budget.estimated_total is None


# Test that a confirmed free attraction contributes zero to the budget
def test_free_attraction_costs_zero():
    assumptions = BudgetAssumptions(
        accommodation_per_room_per_night_cny=200,
        meals_per_person_per_day_cny=50,
        local_transport_per_person_per_day_cny=20
    )

    agent = ItineraryAgent(budget_assumptions=assumptions)

    attractions = [
        create_attraction("A1", 0)
    ]

    budget = agent.calculate_budget(
        attractions=attractions,
        travelers=2,
        days=2
    )

    assert budget.estimated_attraction_entries == 0


# Test that an unknown expense category keeps the total unknown
def test_missing_budget_assumptions_produce_unknown_total():
    agent = ItineraryAgent()

    budget = agent.calculate_budget(
        attractions=[],
        travelers=2,
        days=2
    )

    assert budget.estimated_accommodation is None
    assert budget.estimated_food is None
    assert budget.estimated_local_transport is None
    assert budget.estimated_total is None


# Test that invalid traveler counts are rejected
def test_invalid_traveler_count():
    agent = ItineraryAgent()

    with pytest.raises(ValueError):
        agent.calculate_budget(
            attractions=[],
            travelers=0,
            days=2
        )


# Test that invalid trip durations are rejected
def test_invalid_budget_trip_duration():
    agent = ItineraryAgent()

    with pytest.raises(ValueError):
        agent.calculate_budget(
            attractions=[],
            travelers=2,
            days=0
        )
