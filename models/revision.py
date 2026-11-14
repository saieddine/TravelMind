from pydantic import BaseModel, Field
from models.itinerary import ItineraryPlan
from models.validation import ValidationFinding

class RevisionFeedback(BaseModel):
    """
    Structured feedback sent to the Itinerary Agent
    after the Critic evaluates a proposed itinerary.
    """

    # The itinerary that was evaluated
    previous_plan: ItineraryPlan

    # Problems and observations identified by the Critic
    findings: list[ValidationFinding] = Field(default_factory=list)

    # Additional instructions supplied by the Supervisor, if any
    revision_instructions: list[str] = Field(default_factory=list)