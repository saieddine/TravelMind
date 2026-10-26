
from agents.destination_agent import DestinationAgent
from itinerary import generate_itinerary


class TravelMindOrchestrator:
    def __init__(self):
        self.destination_agent = DestinationAgent()

    def plan_trip(self, trip):
        selected_attractions = self.destination_agent.run(
            destination=trip.destination,
            interests=trip.interests,
        )

        if trip.destination.strip().casefold() != "chengdu":
            return {
                "planner": "TravelMind",
                "workflow_version": "0.3.0",
                "result": {
                    "status": "unsupported_destination",
                    "message": (
                        "This prototype currently supports Chengdu only."
                    ),
                    "supported_destinations": ["Chengdu"],
                },
            }

        result = generate_itinerary(trip, selected_attractions)

        return {
            "planner": "TravelMind",
            "workflow_version": "0.3.0",
            "result": result,
        }


orchestrator = TravelMindOrchestrator()


def plan_trip(trip):
    return orchestrator.plan_trip(trip)
