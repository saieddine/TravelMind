from models.attraction import AttractionInput
from models.budget import BudgetAssumptions
from models.itinerary import ItineraryPlan
from models.validation import ValidationFinding

from agents.itinerary_agent import ItineraryAgent
from agents.critic_agent import CriticAgent


def generate_and_evaluate_itinerary(
    destination: str,
    attractions: list[AttractionInput],
    travelers: int,
    days: int,
    budget_limit_cny: float,
    rooms: int | None = None,
    budget_assumptions: BudgetAssumptions | None = None,
    max_daily_activity_minutes: int = 360,
    preferences: str | None = None,
) -> tuple[ItineraryPlan, list[ValidationFinding]]:
    """
    Generate an itinerary and independently evaluate it.

    This function connects the Itinerary Agent and Critic Agent.
    It does not manage revisions or workflow state.
    """

    # Create the Itinerary Agent
    itinerary_agent = ItineraryAgent(
        max_daily_activity_minutes=max_daily_activity_minutes,
        budget_assumptions=budget_assumptions,
    )

    # Generate the proposed itinerary
    plan = itinerary_agent.generate_itinerary(
        destination=destination,
        attractions=attractions,
        travelers=travelers,
        days=days,
        rooms=rooms,
        preferences=preferences,
    )

    # Create the Critic Agent with the same daily activity limit
    critic_agent = CriticAgent(
        max_daily_activity_minutes=max_daily_activity_minutes
    )

    # Independently validate the generated itinerary
    findings = critic_agent.validate(
        plan=plan,
        travelers=travelers,
        budget_limit_cny=budget_limit_cny,
        expected_days=days,
    )

    # Return the plan and its validation findings
    return plan, findings
