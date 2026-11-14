
import pytest
from pydantic import ValidationError

from models.itinerary import (
    PlannedActivity,
    DayPlan,
    BudgetBreakdown,
    ItineraryPlan,
)


def test_valid_planned_activity():
    activity = PlannedActivity(
        attraction_id="chengdu_001",
        name_en="Example Museum",
        name_zh="示例博物馆",
        duration_minutes=90,
        estimated_cost_cny=50,
        cost_status="estimated",
        selection_reason="Matches cultural interests",
        sequence=1,
    )

    assert activity.estimated_cost_cny == 50
    assert activity.sequence == 1


def test_unknown_attraction_cost_is_allowed():
    activity = PlannedActivity(
        attraction_id="chengdu_002",
        name_en="Example Park",
        name_zh="示例公园",
        duration_minutes=60,
        estimated_cost_cny=None,
        cost_status="unknown",
        selection_reason="Matches nature interests",
        sequence=1,
    )

    assert activity.estimated_cost_cny is None


def test_negative_activity_cost_is_rejected():
    with pytest.raises(ValidationError):
        PlannedActivity(
            attraction_id="chengdu_003",
            name_en="Example",
            name_zh="示例",
            duration_minutes=60,
            estimated_cost_cny=-10,
            cost_status="estimated",
            selection_reason="Test",
            sequence=1,
        )


def test_budget_uses_group_totals():
    budget = BudgetBreakdown(
        estimated_food=300,
        estimated_local_transport=100,
        estimated_accommodation=500,
        estimated_attraction_entries=150,
        estimated_total=1050,
    )

    assert budget.estimated_total == 1050
    assert budget.currency == "CNY"


def test_complete_itinerary_structure():
    activity = PlannedActivity(
        attraction_id="chengdu_001",
        name_en="Example Museum",
        name_zh="示例博物馆",
        duration_minutes=90,
        estimated_cost_cny=50,
        cost_status="estimated",
        selection_reason="Matches cultural interests",
        sequence=1,
    )

    plan = ItineraryPlan(
        destination="Chengdu",
        days=[
            DayPlan(
                day_number=1,
                activities=[activity],
                total_activity_minutes=90,
            )
        ],
        budget=BudgetBreakdown(),
    )

    assert plan.destination == "Chengdu"
    assert len(plan.days) == 1
    assert plan.days[0].activities[0].attraction_id == "chengdu_001"
