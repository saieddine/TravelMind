"""Run Destination + Context Agents together OFFLINE; no network switch exists here."""

import argparse
import json
from agents.destination_agent import DestinationAgent
from agents.context_agent import ContextAgent


def main(argv=None):
    p = argparse.ArgumentParser(description="TravelMind offline handoff demo (zero paid calls)")
    p.add_argument("--text", default="I love history and museums in Xi'an")
    p.add_argument("--scenario", choices=["rain", "sunny", "hot", "cold", "storm"],
                   default="rain", help="SIMULATED conditions, not actual weather")
    p.add_argument("--date", help="Travel date YYYY-MM-DD")
    args = p.parse_args(argv)

    destination = DestinationAgent(max_places=4).run_candidates(args.text, live=False, ai=False)
    context = ContextAgent().run(
        city=destination["request"]["city"],
        travel_date=args.date,
        scenario=args.scenario,
        live=False,
    )
    output = {
        "handoff_version": "stage4-demo-draft",
        "destination": destination,
        "context": context,
        "total_usage": {
            "amap_requests_attempted": (
                destination["usage"]["amap_api_requests_attempted"]
                + context["usage"]["amap_weather_requests_attempted"]
            ),
            "llm_requests_attempted": (
                destination["usage"]["llm_requests_attempted"]
                + context["usage"]["llm_requests_attempted"]
            ),
            "llm_tokens": 0,
        },
        "note": "Demo input is not a real forecast or itinerary; verify team integration contract before wiring API.",
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return output


if __name__ == "__main__":
    main()
