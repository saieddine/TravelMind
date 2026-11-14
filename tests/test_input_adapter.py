import pytest

from agents.input_adapter import convert_destination_places
from models.attraction import AttractionInput


def test_convert_valid_destination_places():
    places = [
        {
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
    ]

    attractions = convert_destination_places(places)

    assert len(attractions) == 1
    assert isinstance(attractions[0], AttractionInput)
    assert attractions[0].id == "A001"


def test_convert_empty_places():
    assert convert_destination_places([]) == []


def test_convert_invalid_place():
    places = [{"id": "A001"}]

    with pytest.raises(ValueError, match="Invalid attraction data"):
        convert_destination_places(places)