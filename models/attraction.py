
from typing import Any, Literal

from pydantic import BaseModel, Field


InformationStatus = Literal["verified", "estimated", "unknown"]


class AttractionInput(BaseModel):
    """
    Represents one recommended attraction received
    from the Destination Agent.
    """

    # Identification
    id: str
    name_zh: str
    name_en: str

    # Location
    city_zh: str
    district_zh: str | None = None
    address_zh: str | None = None
    coordinates: dict[str, Any] | None = None

    # Attraction information
    category: str
    verification_status: str

    # Duration and cost
    duration_minutes: int | None = Field(default=None, gt=0)
    duration_status: InformationStatus

    ticket_price_cny: float | None = Field(default=None, ge=0)
    estimated_cost_cny: float | None = Field(default=None, ge=0)
    cost_status: InformationStatus

    # Recommendation and evidence
    selection_reason: str

    source: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
