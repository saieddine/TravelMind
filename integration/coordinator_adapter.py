"""Additive Coordinator bridge using the existing authoritative TripRequest."""
from copy import deepcopy
from agents.destination_agent import DestinationAgent, canonical_city
from agents.context_agent import ContextAgent
from models import TripRequest
from llm.intent_interpreter import validate_intent


def collect_agent_results(trip: TripRequest, *, destination_agent=None,
                          interpreted_intent=None, scenario=None):
    request = TripRequest.model_validate(trip)
    if interpreted_intent is not None:
        interpreted_intent = validate_intent(interpreted_intent)
        city = interpreted_intent["city"]
        if city is not None and canonical_city(city) != canonical_city(request.destination):
            raise ValueError("LLM city conflicts with the authoritative TripRequest destination")
    agent = destination_agent or DestinationAgent()
    destination = agent.run_candidates(
        "Find attraction candidates", city=request.destination,
        interests=request.interests, live=False, ai=False,
        interpreted_intent=interpreted_intent)
    context = ContextAgent().run(city=request.destination, scenario=scenario, live=False)
    return {"trip": request.model_dump(), "destination": destination, "context": context,
            "selection_scope": "candidates_only", "final_selection_owner": "itinerary_agent",
            "routing": {"status": "not_requested"},
            "usage": {"external_requests_attempted": 0, "llm_requests_attempted": 0, "llm_tokens": 0},
            "usage_scope": "this offline collection only; account for upstream LLM usage separately",
            "trace": [*deepcopy(destination["trace"]), *deepcopy(context["trace"])]}
