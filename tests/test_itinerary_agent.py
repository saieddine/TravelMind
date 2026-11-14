
import pytest

from agents.itinerary_agent import ItineraryAgent
from models.attraction import AttractionInput


# Create a reusable sample attraction for scheduling tests
def create_attraction(
    attraction_id: str,
    name: str,
    duration: int | None,
    cost: float | None = 50.0,
):
    return AttractionInput(
        id=attraction_id,
        name_en=name,
        name_zh="测试景点",
        city_zh="西安市",
        district_zh="雁塔区",
        category="Culture",
        verification_status="curated_sample",
        duration_minutes=duration,
        duration_status="estimated" if duration is not None else "unknown",
        ticket_price_cny=cost,
        estimated_cost_cny=cost,
        cost_status="estimated" if cost is not None else "unknown",
        selection_reason="Selected for testing."
    )


# Test that attractions are distributed across days within the time limit
def test_schedules_attractions_within_daily_limit():
    agent = ItineraryAgent(max_daily_activity_minutes=360)

    attractions = [
        create_attraction("A1", "Museum", 180),
        create_attraction("A2", "Park", 180),
        create_attraction("A3", "Gallery", 120),
    ]

    daily_plans, unassigned = agent.schedule_attractions(attractions, days=2)

    assert len(daily_plans) == 2
    assert daily_plans[0].total_activity_minutes == 360
    assert daily_plans[1].total_activity_minutes == 120
    assert unassigned == []


# Test that an attraction with unknown duration is not scheduled
def test_unknown_duration_is_unassigned():
    agent = ItineraryAgent()

    attractions = [
        create_attraction("A1", "Museum", None)
    ]

    daily_plans, unassigned = agent.schedule_attractions(attractions, days=1)

    assert daily_plans[0].activities == []
    assert len(unassigned) == 1
    assert unassigned[0].attraction_id == "A1"


# Test that an attraction exceeding the daily limit remains unassigned
def test_attraction_exceeding_daily_limit_is_unassigned():
    agent = ItineraryAgent(max_daily_activity_minutes=360)

    attractions = [
        create_attraction("A1", "Full-day attraction", 420)
    ]

    daily_plans, unassigned = agent.schedule_attractions(attractions, days=1)

    assert daily_plans[0].activities == []
    assert len(unassigned) == 1


# Test that duplicate attraction IDs are scheduled only once
def test_duplicate_attraction_is_not_scheduled_twice():
    agent = ItineraryAgent()

    attractions = [
        create_attraction("A1", "Museum", 120),
        create_attraction("A1", "Museum duplicate", 120),
    ]

    daily_plans, unassigned = agent.schedule_attractions(attractions, days=1)

    assert len(daily_plans[0].activities) == 1
    assert daily_plans[0].activities[0].attraction_id == "A1"
    assert unassigned == []


# Test that the daily activity limit can be configured
def test_custom_daily_activity_limit():
    agent = ItineraryAgent(max_daily_activity_minutes=240)

    attractions = [
        create_attraction("A1", "Museum", 180),
        create_attraction("A2", "Park", 120),
    ]

    daily_plans, unassigned = agent.schedule_attractions(attractions, days=1)

    assert daily_plans[0].total_activity_minutes == 180
    assert len(unassigned) == 1


# Test that invalid daily limits are rejected
def test_invalid_daily_activity_limit():
    with pytest.raises(ValueError):
        ItineraryAgent(max_daily_activity_minutes=0)


# Test that invalid trip durations are rejected
def test_invalid_trip_duration():
    agent = ItineraryAgent()

    with pytest.raises(ValueError):
        agent.schedule_attractions([], days=0)
