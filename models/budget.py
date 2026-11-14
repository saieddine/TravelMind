
from pydantic import BaseModel, Field


class BudgetAssumptions(BaseModel):
    """Stores configurable estimates used for trip budgeting."""

    # Estimated accommodation cost for one room per night
    accommodation_per_room_per_night_cny: float | None = Field(
        default=None,
        ge=0
    )

    # Estimated meal cost for one traveler per day
    meals_per_person_per_day_cny: float | None = Field(
        default=None,
        ge=0
    )

    # Estimated local transportation cost for one traveler per day
    local_transport_per_person_per_day_cny: float | None = Field(
        default=None,
        ge=0
    )

    # Assumed maximum number of travelers sharing one room
    people_per_room: int = Field(default=2, ge=1)
