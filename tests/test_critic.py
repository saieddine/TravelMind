import pytest

from agents.critic_agent import CriticAgent
from models.itinerary import (
    ItineraryPlan,
    DayPlan,
    PlannedActivity,
    BudgetBreakdown,
)


@pytest.fixture
def valid_plan():
    """Create a valid two-day itinerary for testing."""

    return ItineraryPlan(
        destination="Beijing",
        days=[
            DayPlan(
                day_number=1,
                activities=[
                    PlannedActivity(
                        attraction_id="A1",
                        name_en="Forbidden City",
                        name_zh="故宫",
                        duration_minutes=120,
                        estimated_cost_cny=60,
                        cost_status="verified",
                        selection_reason="Historical attraction",
                        sequence=1,
                    ),
                ],
                total_activity_minutes=120,
            ),
            DayPlan(
                day_number=2,
                activities=[
                    PlannedActivity(
                        attraction_id="A2",
                        name_en="Temple of Heaven",
                        name_zh="天坛",
                        duration_minutes=90,
                        estimated_cost_cny=30,
                        cost_status="verified",
                        selection_reason="Cultural attraction",
                        sequence=1,
                    ),
                ],
                total_activity_minutes=90,
            ),
        ],
        budget=BudgetBreakdown(
            estimated_food=200,
            estimated_local_transport=100,
            estimated_accommodation=300,
            estimated_attraction_entries=90,
            estimated_total=690,
        ),
    )


def test_valid_itinerary_has_no_findings(valid_plan):
    critic = CriticAgent()

    findings = critic.validate(
        plan=valid_plan,
        travelers=1,
        budget_limit_cny=1000,
        expected_days=2,
    )

    assert findings == []


def test_detects_daily_duration_mismatch(valid_plan):
    critic = CriticAgent()

    valid_plan.days[0].total_activity_minutes = 60

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "DAILY_DURATION_MISMATCH"
        for finding in findings
    )


def test_detects_daily_time_limit_exceeded(valid_plan):
    critic = CriticAgent(max_daily_activity_minutes=60)

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "DAILY_TIME_LIMIT_EXCEEDED"
        for finding in findings
    )


def test_detects_duplicate_attractions(valid_plan):
    critic = CriticAgent()

    duplicate_activity = valid_plan.days[0].activities[0].model_copy(
        update={"sequence": 2}
    )

    valid_plan.days[1].activities.append(duplicate_activity)
    valid_plan.days[1].total_activity_minutes += 120
    valid_plan.budget.estimated_attraction_entries = 150
    valid_plan.budget.estimated_total = 750

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "DUPLICATE_ATTRACTION"
        for finding in findings
    )


def test_detects_incorrect_day_count(valid_plan):
    critic = CriticAgent()

    findings = critic.validate(
        valid_plan,
        expected_days=3,
    )

    assert any(
        finding.rule_id == "INCORRECT_DAY_COUNT"
        for finding in findings
    )


def test_detects_attraction_budget_mismatch(valid_plan):
    critic = CriticAgent()

    valid_plan.budget.estimated_attraction_entries = 200

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "ATTRACTION_BUDGET_MISMATCH"
        for finding in findings
    )


def test_detects_total_budget_mismatch(valid_plan):
    critic = CriticAgent()

    valid_plan.budget.estimated_total = 500

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "TOTAL_BUDGET_MISMATCH"
        for finding in findings
    )


def test_detects_budget_exceeded(valid_plan):
    critic = CriticAgent()

    findings = critic.validate(
        valid_plan,
        budget_limit_cny=500,
    )

    assert any(
        finding.rule_id == "BUDGET_EXCEEDED"
        for finding in findings
    )


def test_reports_unknown_attraction_cost(valid_plan):
    critic = CriticAgent()

    activity = valid_plan.days[0].activities[0]
    activity.estimated_cost_cny = None
    activity.cost_status = "unknown"

    valid_plan.budget.estimated_attraction_entries = None
    valid_plan.budget.estimated_total = None

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "UNKNOWN_ATTRACTION_COST"
        for finding in findings
    )


def test_reports_unassigned_attractions(valid_plan):
    critic = CriticAgent()

    from models.itinerary import UnassignedAttraction

    valid_plan.unassigned_attractions.append(
        UnassignedAttraction(
            attraction_id="A3",
            name_en="Summer Palace",
            reason="No available time",
        )
    )

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "UNASSIGNED_ATTRACTIONS"
        for finding in findings
    )


def test_rejects_invalid_traveler_count(valid_plan):
    critic = CriticAgent()

    with pytest.raises(ValueError):
        critic.validate(valid_plan, travelers=0)


def test_rejects_invalid_budget_limit(valid_plan):
    critic = CriticAgent()

    with pytest.raises(ValueError):
        critic.validate(valid_plan, budget_limit_cny=0)


def test_detects_missing_cost_with_verified_status(valid_plan):
    critic = CriticAgent()

    activity = valid_plan.days[0].activities[0]
    activity.estimated_cost_cny = None
    activity.cost_status = "verified"

    valid_plan.budget.estimated_attraction_entries = None
    valid_plan.budget.estimated_total = None

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "INCONSISTENT_COST_STATUS"
        for finding in findings
    )


def test_detects_known_cost_with_unknown_status(valid_plan):
    critic = CriticAgent()

    activity = valid_plan.days[0].activities[0]
    activity.cost_status = "unknown"

    findings = critic.validate(valid_plan)

    assert any(
        finding.rule_id == "INCONSISTENT_COST_STATUS"
        for finding in findings
    )


def test_detects_incorrect_group_attraction_cost(valid_plan):
    critic = CriticAgent()

    findings = critic.validate(
        valid_plan,
        travelers=3,
    )

    # Expected attraction cost: (60 + 30) * 3 = 270 CNY
    assert any(
        finding.rule_id == "ATTRACTION_BUDGET_MISMATCH"
        for finding in findings
    )
