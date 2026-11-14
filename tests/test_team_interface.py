
from types import SimpleNamespace

import pytest

from agents.team_interface import run_itinerary_task


def sample_place():
    return {
        "id": "A001",
        "name_zh": "兵马俑",
        "name_en": "Terracotta Army",
        "city_zh": "西安",
        "category": "History",
        "verification_status": "curated_sample",
        "duration_minutes": 180,
        "duration_status": "estimated",
        "ticket_price_cny": 120,
        "estimated_cost_cny": 120,
        "cost_status": "estimated",
        "selection_reason": "Historical attraction",
    }


def sample_request():
    return SimpleNamespace(
        destination="Xi'an",
        travelers=2,
        days=2,
        budget=3000,
    )



def test_team_interface_generates_itinerary():
    result = run_itinerary_task(
        request=sample_request(),
        destination_result={"places": [sample_place()]},
    )

    assert result["agent_name"] == "itinerary_agent"
    assert result["status"] in {"success", "partial", "needs_revision"}
    assert "itinerary" in result["data"]
    assert "validation_findings" in result["data"]
    assert isinstance(result["evidence"], list)
    assert isinstance(result["warnings"], list)
    assert isinstance(result["errors"], list)


def test_team_interface_rejects_invalid_destination_result():
    with pytest.raises(ValueError, match="dictionary"):
        run_itinerary_task(
            request=sample_request(),
            destination_result="invalid",
        )


def test_team_interface_rejects_missing_places():
    with pytest.raises(ValueError, match="places list"):
        run_itinerary_task(
            request=sample_request(),
            destination_result={},
        )
