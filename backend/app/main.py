from __future__ import annotations

from typing import Literal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="TravelMind API",
    description="A small multi-agent travel-planning prototype. Costs are sample estimates, not live quotes.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INTERESTS = {"nature", "local food", "culture", "photography", "less crowded"}

# Small, transparent demo dataset. Replace estimates with sourced data as the project grows.
DESTINATIONS = [
    {
        "name": "Chengdu",
        "departure_region": "Xi'an",
        "tags": ["nature", "local food", "culture", "photography"],
        "transport_estimate": 420,
        "daily_cost_estimate": 210,
        "summary": "A food-focused city with cultural sites and access to nearby nature.",
        "places": [
            {"name": "People's Park", "type": "culture", "cost": 0, "hours": 2},
            {"name": "Jinli Ancient Street", "type": "local food", "cost": 60, "hours": 2},
            {"name": "Chengdu Research Base (sample entry estimate)", "type": "nature", "cost": 80, "hours": 4},
            {"name": "Wuhou Shrine (sample entry estimate)", "type": "culture", "cost": 50, "hours": 2},
            {"name": "Local food district", "type": "local food", "cost": 90, "hours": 2},
        ],
    },
    {
        "name": "Lanzhou",
        "departure_region": "Xi'an",
        "tags": ["nature", "local food", "culture", "photography", "less crowded"],
        "transport_estimate": 300,
        "daily_cost_estimate": 175,
        "summary": "Yellow River scenery, local noodles, and a comparatively compact city visit.",
        "places": [
            {"name": "Zhongshan Bridge", "type": "photography", "cost": 0, "hours": 1},
            {"name": "Yellow River riverside", "type": "nature", "cost": 0, "hours": 2},
            {"name": "Gansu Provincial Museum (sample entry estimate)", "type": "culture", "cost": 0, "hours": 3},
            {"name": "Lanzhou noodle restaurant", "type": "local food", "cost": 45, "hours": 1},
            {"name": "Baita Mountain Park", "type": "nature", "cost": 0, "hours": 2},
        ],
    },
    {
        "name": "Luoyang",
        "departure_region": "Xi'an",
        "tags": ["culture", "photography", "local food", "less crowded"],
        "transport_estimate": 260,
        "daily_cost_estimate": 190,
        "summary": "Historic sites, traditional food, and a manageable short city break.",
        "places": [
            {"name": "Luoyi Ancient City", "type": "culture", "cost": 0, "hours": 2},
            {"name": "Longmen Grottoes (sample entry estimate)", "type": "culture", "cost": 90, "hours": 4},
            {"name": "Old Town food streets", "type": "local food", "cost": 65, "hours": 2},
            {"name": "White Horse Temple (sample entry estimate)", "type": "culture", "cost": 35, "hours": 3},
            {"name": "Lijing Gate", "type": "photography", "cost": 0, "hours": 1},
        ],
    },
]

class TripRequest(BaseModel):
    departure_city: str = Field(default="Xi'an", min_length=1, max_length=80)
    budget_cny: int = Field(default=1500, ge=100, le=100000)
    duration_days: int = Field(default=5, ge=1, le=14)
    interests: list[str] = Field(default_factory=lambda: ["nature", "local food", "culture"])
    destination: str | None = None
    pace: Literal["relaxed", "normal", "intensive"] = "normal"

class AgentEvent(BaseModel):
    agent: str
    status: str
    message: str

def destination_score(destination: dict, request: TripRequest) -> float:
    interests = {i.lower().strip() for i in request.interests}
    overlap = len(interests.intersection(destination["tags"]))
    total_estimate = destination["transport_estimate"] + destination["daily_cost_estimate"] * request.duration_days
    affordability = 1.0 if total_estimate <= request.budget_cny else max(0.0, request.budget_cny / total_estimate)
    # Explainable baseline ranking; tune with evaluation data later.
    return overlap * 2.0 + affordability * 3.0

def make_itinerary(destination: dict, request: TripRequest) -> dict:
    places = destination["places"]
    # Deterministic sample scheduler: two attractions per day, avoiding repeats.
    day_plans = []
    daily_allowance = max(0, (request.budget_cny - destination["transport_estimate"]) // request.duration_days)
    pace_count = {"relaxed": 1, "normal": 2, "intensive": 3}[request.pace]
    for day in range(request.duration_days):
        chosen = [places[(day * pace_count + j) % len(places)] for j in range(min(pace_count, len(places)))]
        activity_cost = sum(p["cost"] for p in chosen)
        # Sample per-day non-activity costs; illustrative, not sourced live prices.
        food_local = 85
        lodging = 120
        day_total = activity_cost + food_local + lodging
        day_plans.append({
            "day": day + 1,
            "title": f"Day {day + 1} in {destination['name']}",
            "activities": [
                {
                    "name": p["name"],
                    "category": p["type"],
                    "estimated_cost_cny": p["cost"],
                    "duration_hours": p["hours"],
                    "map_search_url": "https://map.baidu.com/search/" + p["name"].replace(" ", "%20"),
                }
                for p in chosen
            ],
            "estimated_cost_cny": day_total,
            "daily_allowance_cny": daily_allowance,
        })
    total = destination["transport_estimate"] + sum(d["estimated_cost_cny"] for d in day_plans)
    return {
        "destination": destination["name"],
        "summary": destination["summary"],
        "transport_estimate_cny": destination["transport_estimate"],
        "days": day_plans,
        "estimated_total_cny": total,
        "budget_cny": request.budget_cny,
        "budget_remaining_cny": request.budget_cny - total,
        "cost_disclaimer": "All amounts are illustrative sample estimates, not live ticket, hotel, or attraction prices.",
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "TravelMind API"}

@app.get("/api/destinations")
def list_destinations():
    return [{"name": d["name"], "tags": d["tags"], "summary": d["summary"]} for d in DESTINATIONS]

@app.post("/api/plan")
def plan_trip(request: TripRequest):
    events: list[dict] = []
    events.append(AgentEvent(agent="Orchestrator", status="started",
        message="Parsed the trip request and started the planning workflow.").model_dump())

    candidates = DESTINATIONS
    if request.destination:
        matches = [d for d in DESTINATIONS if d["name"].lower() == request.destination.lower().strip()]
        if not matches:
            return {
                "error": f"Destination '{request.destination}' is not in this prototype's dataset.",
                "supported_destinations": [d["name"] for d in DESTINATIONS],
            }
        candidates = matches
        events.append(AgentEvent(agent="Destination Agent", status="completed",
            message=f"Using your requested destination: {matches[0]['name']}.").model_dump())
    else:
        ranked = sorted(candidates, key=lambda d: destination_score(d, request), reverse=True)
        candidates = ranked
        events.append(AgentEvent(agent="Destination Agent", status="completed",
            message=f"Ranked {len(candidates)} supported destinations using interest overlap and estimated affordability.").model_dump())

    selected = candidates[0]
    events.append(AgentEvent(agent="Itinerary Agent", status="working",
        message=f"Building a {request.duration_days}-day itinerary for {selected['name']}.").model_dump())
    itinerary = make_itinerary(selected, request)

    # Validation agent uses deterministic Python arithmetic, not LLM self-judgment.
    over_budget = itinerary["estimated_total_cny"] > request.budget_cny
    validation = {
        "valid": not over_budget,
        "budget_ok": not over_budget,
        "estimated_total_cny": itinerary["estimated_total_cny"],
        "budget_cny": request.budget_cny,
        "issues": [] if not over_budget else [
            f"Estimated total exceeds the budget by {itinerary['estimated_total_cny'] - request.budget_cny} CNY."
        ],
        "note": "This first version validates the budget only. Real opening hours, travel times, weather, and live prices are not yet verified."
    }
    events.append(AgentEvent(agent="Validation Agent", status="completed",
        message="Checked estimated total against the requested budget.").model_dump())
    events.append(AgentEvent(agent="Orchestrator", status="completed",
        message="Returned the itinerary, estimate, and validation result.").model_dump())

    return {
        "trip_request": request.model_dump(),
        "destination_candidates": [
            {"name": d["name"], "score": round(destination_score(d, request), 2),
             "estimated_transport_cny": d["transport_estimate"],
             "estimated_total_cny": d["transport_estimate"] + d["daily_cost_estimate"] * request.duration_days}
            for d in candidates
        ],
        "itinerary": itinerary,
        "validation": validation,
        "agent_events": events,
    }
