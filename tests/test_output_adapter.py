
from models.attraction import AttractionInput
from models.itinerary import ItineraryPlan, DayPlan, BudgetBreakdown
from models.validation import ValidationFinding
from agents.output_adapter import build_itinerary_agent_result


def sample_attraction():
    return AttractionInput(
        id="A001",
        name_zh="兵马俑",
        name_en="Terracotta Army",
        city_zh="西安",
        category="History",
        verification_status="curated_sample",
        duration_minutes=180,
        duration_status="estimated",
        estimated_cost_cny=120,
        cost_status="estimated",
        selection_reason="Historical attraction",
        source={
            "provider": "Local dataset",
            "source_type": "local_dataset",
            "verification_status": "curated_sample",
        },
    )


def sample_plan():
    return ItineraryPlan(
        destination="Xi'an",
        days=[DayPlan(day_number=1)],
        budget=BudgetBreakdown(),
    )


def test_output_contains_required_agent_result_fields():
    result = build_itinerary_agent_result(
        sample_plan(), [], [sample_attraction()]
    )

    assert set(result) == {
        "agent_name", "status", "data",
        "evidence", "warnings", "errors", "next_action",
    }
    assert result["agent_name"] == "itinerary_agent"
    assert result["status"] == "success"


def test_output_preserves_attraction_evidence():
    result = build_itinerary_agent_result(
        sample_plan(), [], [sample_attraction()]
    )

    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["source"] == "Local dataset"
    assert result["evidence"][0]["source_type"] == "local_dataset"
    assert result["evidence"][0]["verification_status"] == "curated_sample"


def test_output_marks_errors_as_needing_revision():
    finding = ValidationFinding(
        rule_id="BUDGET_EXCEEDED",
        severity="error",
        message="The budget limit was exceeded.",
    )

    result = build_itinerary_agent_result(
        sample_plan(), [finding], [sample_attraction()]
    )

    assert result["status"] == "needs_revision"
    assert result["next_action"] == "revise_itinerary"
    assert len(result["errors"]) == 1
