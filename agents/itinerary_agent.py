# Import attraction and itinerary models
from models.attraction import AttractionInput
from models.itinerary import (
    PlannedActivity,
    DayPlan,
    UnassignedAttraction,
    BudgetBreakdown,
    ItineraryPlan,
)
from models.revision import RevisionFeedback
# Import configurable budget assumptions
from models.budget import BudgetAssumptions
import json
from agents.llm_client import ask_llm


class ItineraryAgent:
    """Creates daily schedules and estimates trip budgets."""

    def __init__(
        self,
        max_daily_activity_minutes: int = 360,
        budget_assumptions: BudgetAssumptions | None = None
    ):
        # Reject invalid daily activity limits
        if max_daily_activity_minutes <= 0:
            raise ValueError("Daily activity limit must be greater than zero.")

        # Store the configurable daily activity limit
        self.max_daily_activity_minutes = max_daily_activity_minutes

        # Store supplied budget assumptions or use unknown defaults
        self.budget_assumptions = budget_assumptions or BudgetAssumptions()


    def prioritize_attractions(
        self,
        attractions: list[AttractionInput],
        preferences: str | None = None,
    ) -> list[AttractionInput]:
        # Keep the original order if there are not enough attractions.
        if len(attractions) < 2:
            return attractions

        attraction_data = [
            {
                "id": item.id,
                "name": item.name_en,
                "category": item.category,
                "location": item.address_zh or item.district_zh or item.city_zh,
                "reason": item.selection_reason,
                "duration_minutes": item.duration_minutes,
                "cost_cny": item.estimated_cost_cny,
            }
            for item in attractions
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a travel itinerary planning assistant. "
                    "Prioritize attractions based on user preferences, "
                    "attraction relevance, and available information. "
                    "Do not invent facts or modify attraction data. "
                    "Return valid JSON only, using this format: "
                    '{"ordered_attraction_ids": ["id1", "id2"]}. '
                    "Include every supplied attraction ID exactly once."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User preferences: {preferences or 'Not specified'}\n"
                    f"Attractions: {json.dumps(attraction_data, ensure_ascii=False)}"
                ),
            },
        ]

        # Ask the LLM to prioritize the attractions.
        response = ask_llm(messages, max_tokens=700)

        if not response:
            return attractions

        try:
            # Extract the ordered IDs from the AI response.
            result = json.loads(response)
            ordered_ids = result["ordered_attraction_ids"]

            original_ids = [item.id for item in attractions]

            # Reject incomplete, duplicated, or invented IDs.
            if (
                not isinstance(ordered_ids, list)
                or len(ordered_ids) != len(original_ids)
                or len(set(ordered_ids)) != len(original_ids)
                or set(ordered_ids) != set(original_ids)
            ):
                return attractions

            attraction_lookup = {
                item.id: item for item in attractions
            }

            return [
                attraction_lookup[item_id]
                for item_id in ordered_ids
            ]

        except (ValueError, KeyError, TypeError):
            # Preserve the original order if the AI response is invalid.
            return attractions


    def schedule_attractions(
        self,
        attractions: list[AttractionInput],
        days: int
    ):
        # Reject invalid trip durations
        if days < 1:
            raise ValueError("Trip duration must be at least one day.")

        # Create an empty schedule for every trip day
        daily_plans = [
            DayPlan(day_number=day)
            for day in range(1, days + 1)
        ]

        # Track attractions that cannot be scheduled
        unassigned = []

        # Track attraction IDs to prevent duplicate scheduling
        scheduled_ids = set()

        # Process attractions in the order provided by the Destination Agent
        for attraction in attractions:

            # Skip attractions that have already been scheduled
            if attraction.id in scheduled_ids:
                continue

            # Do not schedule attractions with unknown duration
            if attraction.duration_minutes is None:
                unassigned.append(
                    UnassignedAttraction(
                        attraction_id=attraction.id,
                        name_en=attraction.name_en,
                        reason="Duration is unknown, so scheduling is not possible."
                    )
                )
                continue

            # Try to place the attraction into the earliest day with enough time
            placed = False

            for day_plan in daily_plans:

                # Calculate the remaining activity time for this day
                remaining_minutes = (
                    self.max_daily_activity_minutes
                    - day_plan.total_activity_minutes
                )

                if attraction.duration_minutes <= remaining_minutes:

                    # Create the scheduled activity
                    activity = PlannedActivity(
                        attraction_id=attraction.id,
                        name_en=attraction.name_en,
                        name_zh=attraction.name_zh,
                        duration_minutes=attraction.duration_minutes,
                        estimated_cost_cny=attraction.estimated_cost_cny,
                        cost_status=attraction.cost_status,
                        selection_reason=attraction.selection_reason,
                        sequence=len(day_plan.activities) + 1
                    )

                    # Add the activity and update the day's total duration
                    day_plan.activities.append(activity)
                    day_plan.total_activity_minutes += attraction.duration_minutes

                    # Mark the attraction as scheduled
                    scheduled_ids.add(attraction.id)
                    placed = True
                    break

            # Record attractions that could not fit into the itinerary
            if not placed:
                unassigned.append(
                    UnassignedAttraction(
                        attraction_id=attraction.id,
                        name_en=attraction.name_en,
                        reason="No available day has enough remaining time."
                    )
                )

        # Return the completed schedule and unassigned attractions
        return daily_plans, unassigned

    def calculate_budget(
        self,
        attractions: list[AttractionInput],
        travelers: int,
        days: int,
        rooms: int | None = None
    ) -> BudgetBreakdown:

        # Reject invalid traveler and trip counts
        if travelers < 1:
            raise ValueError("Number of travelers must be at least one.")

        if days < 1:
            raise ValueError("Trip duration must be at least one day.")

        if rooms is not None and rooms < 1:
            raise ValueError("Number of rooms must be at least one.")

        # Calculate the number of hotel nights
        nights = max(days - 1, 0)

        # Calculate the required rooms if not explicitly provided
        if rooms is None:
            rooms = (
                travelers + self.budget_assumptions.people_per_room - 1
            ) // self.budget_assumptions.people_per_room

        # Calculate group accommodation cost
        hotel_rate = (
            self.budget_assumptions.accommodation_per_room_per_night_cny
        )

        accommodation = (
            hotel_rate * rooms * nights
            if hotel_rate is not None
            else None
        )

        # Calculate group meal cost
        meal_rate = self.budget_assumptions.meals_per_person_per_day_cny

        food = (
            meal_rate * travelers * days
            if meal_rate is not None
            else None
        )

        # Calculate group local transportation cost
        transport_rate = (
            self.budget_assumptions.local_transport_per_person_per_day_cny
        )

        transport = (
            transport_rate * travelers * days
            if transport_rate is not None
            else None
        )

        # Calculate attraction entry costs for the entire group
        if all(
            attraction.estimated_cost_cny is not None
            for attraction in attractions
        ):
            attraction_entries = sum(
                attraction.estimated_cost_cny * travelers
                for attraction in attractions
            )
        else:
            # Keep the total unknown if any attraction cost is unknown
            attraction_entries = None

        # Calculate the total only when every expense category is known
        expense_categories = [
            accommodation,
            food,
            transport,
            attraction_entries
        ]

        if all(cost is not None for cost in expense_categories):
            estimated_total = sum(expense_categories)
        else:
            estimated_total = None

        # Return the structured group budget
        return BudgetBreakdown(
            estimated_food=food,
            estimated_local_transport=transport,
            estimated_accommodation=accommodation,
            estimated_attraction_entries=attraction_entries,
            estimated_total=estimated_total
        )


    def generate_itinerary(
    self,
    destination: str,
    attractions: list[AttractionInput],
    travelers: int,
    days: int,
    rooms: int | None = None,
    preferences: str | None = None,
    ) -> ItineraryPlan:

        # Reject an empty destination
        if not destination.strip():
            raise ValueError("Destination cannot be empty.")

        # Let the AI prioritize attractions before deterministic scheduling.
        prioritized_attractions = self.prioritize_attractions(
            attractions=attractions,
            preferences=preferences,
        )

        # Keep scheduling and time-limit enforcement in Python.
        daily_plans, unassigned = self.schedule_attractions(
           attractions=prioritized_attractions,
           days=days
        )

        # Collect the IDs of attractions that were actually scheduled
        scheduled_ids = {
            activity.attraction_id
            for day_plan in daily_plans
            for activity in day_plan.activities
        }

        # Keep only the first occurrence of each scheduled attraction
        scheduled_attractions = []
        processed_ids = set()

        for attraction in attractions:
            if (
                attraction.id in scheduled_ids
                and attraction.id not in processed_ids
            ):
                scheduled_attractions.append(attraction)
                processed_ids.add(attraction.id)

        # Calculate the budget using scheduled attractions only
        budget = self.calculate_budget(
            attractions=scheduled_attractions,
            travelers=travelers,
            days=days,
            rooms=rooms
        )

        # Record the assumptions used in the itinerary
        assumptions = [
            f"Maximum daily activity time: "
            f"{self.max_daily_activity_minutes} minutes.",
            "Attraction costs are calculated per person and multiplied "
            "by the number of travelers.",
            "Accommodation is calculated using days minus one hotel nights.",
            "Meals and local transportation use configurable daily estimates.",
            "Intercity transportation is excluded from the budget.",
            "Unknown costs are not treated as zero."
        ]

        # Add a warning when some recommended attractions were not scheduled
        warnings = []

        if unassigned:
            warnings.append(
                f"{len(unassigned)} recommended attraction(s) "
                "could not be scheduled."
            )

        # Warn when the complete budget cannot be calculated
        if budget.estimated_total is None:
            warnings.append(
                "The complete trip budget is unavailable because "
                "one or more expense categories have unknown costs."
            )

        # Return the complete structured itinerary
        return ItineraryPlan(
            destination=destination,
            days=daily_plans,
            budget=budget,
            unassigned_attractions=unassigned,
            assumptions=assumptions,
            warnings=warnings
        )

    def revise_itinerary(
        self,
        destination: str,
        attractions: list[AttractionInput],
        travelers: int,
        days: int,
        feedback: RevisionFeedback,
        rooms: int | None = None,
    ) -> ItineraryPlan:
        """
        Apply safe, deterministic corrections to a previous itinerary.

        The Supervisor controls whether another revision is allowed.
        """

        # Validate the revision inputs
        if travelers < 1:
            raise ValueError("Number of travelers must be at least one.")

        if days < 1:
            raise ValueError("Trip duration must be at least one day.")

        if not destination.strip():
            raise ValueError("Destination cannot be empty.")

        # Work on a copy so the previous plan remains unchanged
        revised_plan = feedback.previous_plan.model_copy(deep=True)

        # Track attraction IDs to prevent duplicate scheduling
        scheduled_ids = set()

        # Remove duplicate activities and correct their sequence
        for day_index, day_plan in enumerate(revised_plan.days, start=1):
            day_plan.day_number = day_index

            unique_activities = []

            for activity in day_plan.activities:
                if activity.attraction_id in scheduled_ids:
                    continue

                scheduled_ids.add(activity.attraction_id)
                unique_activities.append(activity)

            day_plan.activities = unique_activities

            # Correct activity sequence numbers
            for sequence, activity in enumerate(
                day_plan.activities,
                start=1
            ):
                activity.sequence = sequence

            # Recalculate the daily activity duration
            day_plan.total_activity_minutes = sum(
                activity.duration_minutes or 0
                for activity in day_plan.activities
            )

        # Collect scheduled attraction costs
        scheduled_activities = [
            activity
            for day_plan in revised_plan.days
            for activity in day_plan.activities
        ]

        # Recalculate group attraction costs
        if all(
            activity.estimated_cost_cny is not None
            for activity in scheduled_activities
        ):
            attraction_cost = sum(
                activity.estimated_cost_cny * travelers
                for activity in scheduled_activities
            )
        else:
            attraction_cost = None

        revised_plan.budget.estimated_attraction_entries = attraction_cost

        # Recalculate the complete group budget
        expense_categories = [
            revised_plan.budget.estimated_food,
            revised_plan.budget.estimated_local_transport,
            revised_plan.budget.estimated_accommodation,
            attraction_cost,
        ]

        if all(cost is not None for cost in expense_categories):
            revised_plan.budget.estimated_total = sum(expense_categories)
        else:
            revised_plan.budget.estimated_total = None

        # Identify findings that this deterministic revision cannot resolve
        repairable_rules = {
            "DUPLICATE_ATTRACTION",
            "INCORRECT_DAY_NUMBER",
            "INCORRECT_ACTIVITY_SEQUENCE",
            "DAILY_DURATION_MISMATCH",
            "ATTRACTION_BUDGET_MISMATCH",
            "TOTAL_BUDGET_MISMATCH",
        }

        unresolved_findings = [
            finding
            for finding in feedback.findings
            if finding.rule_id not in repairable_rules
            and finding.severity in ("warning", "error")
        ]

        # Preserve unresolved issues transparently
        for finding in unresolved_findings:
            revised_plan.warnings.append(
                f"Revision could not automatically resolve "
                f"{finding.rule_id}: {finding.message}"
            )

        # Preserve additional Supervisor instructions
        revised_plan.assumptions.extend(
            feedback.revision_instructions
        )

        return revised_plan
