
import pytest
from pydantic import ValidationError

from models.attraction import AttractionInput


def test_valid_attraction():
    attraction = AttractionInput(
        id="example_001",
        name_zh="示例景点",
        name_en="Example Attraction",
        city_zh="成都",
        category="museum",
        verification_status="unverified",
        duration_minutes=90,
        duration_status="estimated",
        ticket_price_cny=None,
        estimated_cost_cny=None,
        cost_status="unknown",
        selection_reason="Matches history interests"
    )

    assert attraction.duration_minutes == 90
    assert attraction.cost_status == "unknown"
    assert attraction.estimated_cost_cny is None


def test_unknown_cost_is_allowed():
    attraction = AttractionInput(
        id="example_002",
        name_zh="测试景点",
        name_en="Test Attraction",
        city_zh="成都",
        category="park",
        verification_status="unverified",
        duration_minutes=None,
        duration_status="unknown",
        estimated_cost_cny=None,
        cost_status="unknown",
        selection_reason="Matches nature interests"
    )

    assert attraction.estimated_cost_cny is None
    assert attraction.duration_minutes is None


def test_negative_cost_is_rejected():
    with pytest.raises(ValidationError):
        AttractionInput(
            id="example_003",
            name_zh="测试景点",
            name_en="Test Attraction",
            city_zh="成都",
            category="museum",
            verification_status="unverified",
            duration_minutes=60,
            duration_status="estimated",
            estimated_cost_cny=-50,
            cost_status="estimated",
            selection_reason="Test"
        )


def test_negative_duration_is_rejected():
    with pytest.raises(ValidationError):
        AttractionInput(
            id="example_004",
            name_zh="测试景点",
            name_en="Test Attraction",
            city_zh="成都",
            category="museum",
            verification_status="unverified",
            duration_minutes=-30,
            duration_status="estimated",
            estimated_cost_cny=50,
            cost_status="estimated",
            selection_reason="Test"
        )
