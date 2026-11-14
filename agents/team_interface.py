
from typing import Any

from agents.input_adapter import convert_destination_places
from agents.itinerary_pipeline import generate_and_evaluate_itinerary
from agents.output_adapter import build_itinerary_agent_result
from models.budget import BudgetAssumptions


def run_itinerary_task(
    request: Any,
    destination_result: dict,
    budget_assumptions: BudgetAssumptions | None = None,
) -> dict:
    """
    Run itinerary generation, validation, and result packaging.

    The Supervisor remains responsible for workflow state,
    revision limits, and deciding the next workflow step.
    """

    # Read the trip details from the team's request.
    destination = request.destination
    travelers = request.travelers
    days = request.days
    budget_limit_cny = request.budget

    # Read optional user preferences without requiring them in the team request model.
    preferences = getattr(request, "preferences", None)

    # Check the Destination Agent response.
    if not isinstance(destination_result, dict):
        raise ValueError("Destination Agent result must be a dictionary.")

    places = destination_result.get("places")

    if not isinstance(places, list):
        raise ValueError("Destination Agent result must contain a places list.")

    # Convert destination recommendations into validated attraction models.
    attractions = convert_destination_places(places)

    # Generate the itinerary and independently validate it.
    plan, findings = generate_and_evaluate_itinerary(
        destination=destination,
        attractions=attractions,
        travelers=travelers,
        days=days,
        budget_limit_cny=budget_limit_cny,
        budget_assumptions=budget_assumptions,
        preferences=preferences,
    )

    # Package the output in the team's agreed AgentResult structure.
    return build_itinerary_agent_result(
        plan=plan,
        findings=findings,
        attractions=attractions,
    )
