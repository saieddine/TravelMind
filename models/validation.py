from typing import Literal
from pydantic import BaseModel

class ValidationFinding(BaseModel):
    """One issue or observation identified by the Critic Agent."""

    #Identifies the validation rule, e.g. BUDGET_EXCEEDED
    rule_id: str
    #How serious the finding is
    severity: Literal["info", "warning", "error"]
    #Explains the detected issue
    message: str
    #Identifies the affected part of the itinerary
    field_path: str | None = None
    #Gives the Itinerary Agent an actionable correction
    suggested_correction: str | None = None