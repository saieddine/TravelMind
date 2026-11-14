
from typing import Literal

from pydantic import BaseModel, Field


class PlannedActivity(BaseModel):
    """One attraction or activity scheduled into a trip day."""

    attraction_id: str
    name_en: str
    name_zh: str

    duration_minutes: int | None = Field(default=None, gt=0)

    # Individual attraction cost, not group cost.
    estimated_cost_cny: float | None = Field(default=None, ge=0)
    cost_status: Literal["verified", "estimated", "unknown"]

    selection_reason: str
    sequence: int = Field(ge=1)


class DayPlan(BaseModel):
    """Activities scheduled for one day."""

    day_number: int = Field(ge=1)
    activities: list[PlannedActivity] = Field(default_factory=list)
    total_activity_minutes: int = Field(default=0, ge=0)


class UnassignedAttraction(BaseModel):
    """An attraction that was not placed in the itinerary."""

    attraction_id: str
    name_en: str
    reason: str


class BudgetBreakdown(BaseModel):
    """Estimated trip expenses. All amounts are group totals."""

    estimated_food: float | None = Field(default=None, ge=0)
    estimated_local_transport: float | None = Field(default=None, ge=0)
    estimated_accommodation: float | None = Field(default=None, ge=0)
    estimated_attraction_entries: float | None = Field(default=None, ge=0)

    estimated_total: float | None = Field(default=None, ge=0)

    currency: Literal["CNY"] = "CNY"


class ItineraryPlan(BaseModel):
    """Complete structured output from the Itinerary Agent."""

    destination: str
    days: list[DayPlan]

    budget: BudgetBreakdown

    unassigned_attractions: list[UnassignedAttraction] = Field(
        default_factory=list
    )

    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
