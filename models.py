
from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    origin: str = Field(
        min_length=1,
        description="City where the trip begins",
    )

    destination: str = Field(
        min_length=1,
        description="Destination city",
    )

    days: int = Field(
        ge=1,
        le=30,
        description="Trip duration in days",
    )

    budget: float = Field(
        gt=0,
        description="Total trip budget in Chinese yuan",
    )

    travelers: int = Field(
        default=1,
        ge=1,
        le=20,
        description="Number of travelers",
    )

    interests: list[str] = Field(
        default_factory=list,
        description="Interests such as food, nature, or culture",
    )
