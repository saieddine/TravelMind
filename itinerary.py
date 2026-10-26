
from math import ceil


FOOD_PER_PERSON_PER_DAY = 120
LOCAL_TRANSPORT_PER_PERSON_PER_DAY = 50
ACCOMMODATION_PER_ROOM_PER_NIGHT = 250
TRAVEL_HOURS_PER_DAY = 8


def generate_itinerary(trip, selected_attractions):
    """Schedule agent-selected attractions and estimate trip costs."""

    if trip.destination.strip().casefold() != "chengdu":
        return {
            "status": "unsupported_destination",
            "message": "This prototype currently supports Chengdu only.",
            "supported_destinations": ["Chengdu"],
        }

    daily_plans = [
        {
            "day": day,
            "activities": [],
            "planned_activity_hours": 0,
        }
        for day in range(1, trip.days + 1)
    ]

    unassigned = []

    for place in selected_attractions:
        eligible_days = [
            day for day in daily_plans
            if day["planned_activity_hours"] + place["duration_hours"]
            <= TRAVEL_HOURS_PER_DAY
        ]

        if not eligible_days:
            unassigned.append(place["name"])
            continue

        target_day = min(
            eligible_days,
            key=lambda day: day["planned_activity_hours"],
        )

        target_day["activities"].append({
            "name": place["name"],
            "duration_hours": place["duration_hours"],
            "estimated_entry_cost_per_person": place["entry_cost"],
        })

        target_day["planned_activity_hours"] += place["duration_hours"]

    rooms_needed = ceil(trip.travelers / 2)
    nights = max(trip.days - 1, 0)

    food_cost = (
        FOOD_PER_PERSON_PER_DAY * trip.days * trip.travelers
    )
    local_transport_cost = (
        LOCAL_TRANSPORT_PER_PERSON_PER_DAY
        * trip.days
        * trip.travelers
    )
    accommodation_cost = (
        ACCOMMODATION_PER_ROOM_PER_NIGHT * nights * rooms_needed
    )
    entry_cost = (
        sum(place["entry_cost"] for place in selected_attractions)
        * trip.travelers
    )

    estimated_total = (
        food_cost
        + local_transport_cost
        + accommodation_cost
        + entry_cost
    )

    return {
        "status": "success",
        "destination": "Chengdu",
        "days": trip.days,
        "travelers": trip.travelers,
        "selected_attractions": [
            place["name"] for place in selected_attractions
        ],
        "itinerary": daily_plans,
        "unassigned_attractions": unassigned,
        "budget": {
            "currency": "CNY",
            "user_budget": trip.budget,
            "estimated_food": food_cost,
            "estimated_local_transport": local_transport_cost,
            "estimated_accommodation": accommodation_cost,
            "estimated_attraction_entries": entry_cost,
            "estimated_total": estimated_total,
            "remaining_budget": round(
                trip.budget - estimated_total, 2
            ),
            "within_budget": estimated_total <= trip.budget,
            "intercity_transport_included": False,
            "note": (
                "Illustrative estimates only. Verify actual prices "
                "and transport costs before traveling."
            ),
        },
    }
