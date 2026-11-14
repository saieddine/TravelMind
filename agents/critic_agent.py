from models.itinerary import ItineraryPlan
from models.validation import ValidationFinding
import json
from agents.llm_client import ask_llm

class CriticAgent:
    """Independently validates an itinerary and reports problems."""

    def __init__(self, max_daily_activity_minutes: int = 360):
        #Reject invalid daily activity limits
        if max_daily_activity_minutes <= 0:
            raise ValueError("Daily activity limit must be greater than zero.")

        self.max_daily_activity_minutes = max_daily_activity_minutes

    def review_quality(
        self,
        plan: ItineraryPlan,
    ) -> list[ValidationFinding]:
        # Prepare the itinerary data for the AI review.
        itinerary_data = plan.model_dump()

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an independent travel itinerary quality reviewer. "
                    "Evaluate the itinerary's activity variety, daily pacing, "
                    "repetition, and overall coherence. "
                    "Only use information present in the itinerary. "
                    "Do not invent travel times, distances, opening hours, "
                    "or missing facts. "
                    "Do not repeat objective errors such as budget mismatches "
                    "or duration-limit violations. "
                    "Return valid JSON only in this format: "
                    '{"findings": [{"severity": "info", '
                    '"message": "Explanation", '
                    '"suggested_correction": "Actionable suggestion"}]}. '
                    "Severity must be info or warning. "
                    "Return an empty findings list if there are no meaningful issues."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    itinerary_data,
                    ensure_ascii=False,
                ),
            },
        ]

        # Ask the AI to evaluate itinerary quality.
        response = ask_llm(messages, max_tokens=700)

        if not response:
            return []

        try:
            # Parse the AI response.
            result = json.loads(response)
            ai_findings = result.get("findings", [])

            if not isinstance(ai_findings, list):
                return []

            findings = []

            for item in ai_findings:
                if not isinstance(item, dict):
                    continue

                severity = item.get("severity")
                message = item.get("message")

                # Accept only supported finding values.
                if severity not in ("info", "warning"):
                    continue

                if not isinstance(message, str) or not message.strip():
                    continue

                suggestion = item.get("suggested_correction")

                if not isinstance(suggestion, str):
                    suggestion = None

                findings.append(
                    ValidationFinding(
                        rule_id="AI_QUALITATIVE_REVIEW",
                        severity=severity,
                        message=message,
                        field_path=None,
                        suggested_correction=suggestion,
                    )
                )

            return findings

        except (ValueError, TypeError, AttributeError):
            # Ignore invalid AI responses without interrupting validation.
            return []

    def validate(
        self,
        plan: ItineraryPlan,
        travelers: int = 1,
        budget_limit_cny: float | None = None,
        expected_days: int | None = None
    ) -> list[ValidationFinding]:

        #Validate the supplied parameters
        if travelers < 1:
            raise ValueError("Number of travelers must be at least one.")

        if budget_limit_cny is not None and budget_limit_cny <= 0:
            raise ValueError("Budget limit must be greater than zero.")

        if expected_days is not None and expected_days < 1:
            raise ValueError("Expected trip duration must be at least one day.")

        findings = []

        #Check whether the itinerary contains the requested number of days
        if expected_days is not None and len(plan.days) != expected_days:
            findings.append(
                ValidationFinding(
                    rule_id="INCORRECT_DAY_COUNT",
                    severity="error",
                    message=(
                        f"Expected {expected_days} days, "
                        f"but the itinerary contains {len(plan.days)}."
                    ),
                    field_path="days",
                    suggested_correction=(
                        "Generate exactly the requested number of trip days."
                    )
                )
            )

        #Track attraction IDs to detect duplicate scheduling
        scheduled_ids = set()

        #Track attraction costs for independent budget verification
        attraction_costs = []
        all_attraction_costs_known = True

        #Independently inspect each day
        for index, day in enumerate(plan.days, start=1):

            #Check day numbering
            if day.day_number != index:
                findings.append(
                    ValidationFinding(
                        rule_id="INCORRECT_DAY_NUMBER",
                        severity="error",
                        message=(
                            f"Expected day number {index}, "
                            f"but found day {day.day_number}."
                        ),
                        field_path=f"days[{index - 1}].day_number",
                        suggested_correction=(
                            "Number itinerary days consecutively, starting at 1."
                        )
                    )
                )

            calculated_minutes = 0

            # Check every activity independently
            for activity_index, activity in enumerate(day.activities):

                activity_path = (
                    f"days[{index - 1}].activities[{activity_index}]"
                )

                # Detect duplicate attractions
                if activity.attraction_id in scheduled_ids:
                    findings.append(
                        ValidationFinding(
                            rule_id="DUPLICATE_ATTRACTION",
                            severity="error",
                            message=(
                                f"Attraction '{activity.name_en}' "
                                "appears more than once."
                            ),
                            field_path=f"{activity_path}.attraction_id",
                            suggested_correction=(
                                "Remove the duplicate attraction."
                            )
                        )
                    )
                else:
                    scheduled_ids.add(activity.attraction_id)

                # Check activity sequence
                expected_sequence = activity_index + 1

                if activity.sequence != expected_sequence:
                    findings.append(
                        ValidationFinding(
                            rule_id="INCORRECT_ACTIVITY_SEQUENCE",
                            severity="error",
                            message=(
                                f"Expected sequence {expected_sequence}, "
                                f"but found {activity.sequence}."
                            ),
                            field_path=f"{activity_path}.sequence",
                            suggested_correction=(
                                "Renumber activities consecutively within each day."
                            )
                        )
                    )

                # Recalculate daily activity duration
                if activity.duration_minutes is None:
                    findings.append(
                        ValidationFinding(
                            rule_id="UNKNOWN_ACTIVITY_DURATION",
                            severity="warning",
                            message=(
                                f"Duration for '{activity.name_en}' is unknown."
                            ),
                            field_path=f"{activity_path}.duration_minutes",
                            suggested_correction=(
                                "Obtain a reliable duration estimate "
                                "before scheduling this activity."
                            )
                        )
                    )
                else:
                    calculated_minutes += activity.duration_minutes


                # Collect attraction costs for group-budget verification
                if activity.estimated_cost_cny is None:
                    all_attraction_costs_known = False

                    findings.append(
                        ValidationFinding(
                            rule_id="UNKNOWN_ATTRACTION_COST",
                            severity="warning",
                            message=(
                                f"Cost for '{activity.name_en}' is unknown."
                            ),
                            field_path=f"{activity_path}.estimated_cost_cny",
                            suggested_correction=(
                                "Obtain a verified or estimated cost. "
                                "Do not treat an unknown cost as zero."
                            )
                        )
                    )

                    # An unknown numerical cost must have an unknown status
                    if activity.cost_status != "unknown":
                        findings.append(
                            ValidationFinding(
                                rule_id="INCONSISTENT_COST_STATUS",
                                severity="error",
                                message=(
                                    f"'{activity.name_en}' has no cost value "
                                    f"but its status is '{activity.cost_status}'."
                                ),
                                field_path=f"{activity_path}.cost_status",
                                suggested_correction=(
                                    "Set cost_status to 'unknown' when the cost is None."
                                )
                            )
                        )

                else:
                    attraction_costs.append(
                        activity.estimated_cost_cny * travelers
                    )

                    # A known numerical cost cannot have an unknown status
                    if activity.cost_status == "unknown":
                        findings.append(
                            ValidationFinding(
                                rule_id="INCONSISTENT_COST_STATUS",
                                severity="error",
                                message=(
                                    f"'{activity.name_en}' has a cost value "
                                    "but its status is unknown."
                                ),
                                field_path=f"{activity_path}.cost_status",
                                suggested_correction=(
                                    "Set cost_status to 'estimated' or 'verified' "
                                    "when a numerical cost is available."
                                )
                            )
                        )


            # Compare the calculated duration with the stored duration
            if day.total_activity_minutes != calculated_minutes:
                findings.append(
                    ValidationFinding(
                        rule_id="DAILY_DURATION_MISMATCH",
                        severity="error",
                        message=(
                            f"Day {day.day_number} reports "
                            f"{day.total_activity_minutes} minutes, "
                            f"but its activities total {calculated_minutes} minutes."
                        ),
                        field_path=(
                            f"days[{index - 1}].total_activity_minutes"
                        ),
                        suggested_correction=(
                            "Recalculate the daily total from the activity durations."
                        )
                    )
                )

            # Check the maximum allowed daily activity duration
            if calculated_minutes > self.max_daily_activity_minutes:
                findings.append(
                    ValidationFinding(
                        rule_id="DAILY_TIME_LIMIT_EXCEEDED",
                        severity="error",
                        message=(
                            f"Day {day.day_number} contains "
                            f"{calculated_minutes} activity minutes, "
                            f"exceeding the limit of "
                            f"{self.max_daily_activity_minutes} minutes."
                        ),
                        field_path=f"days[{index - 1}].activities",
                        suggested_correction=(
                            "Move some activities to another day "
                            "or reduce the scheduled activity time."
                        )
                    )
                )

        # Independently verify attraction entry costs
        reported_attraction_cost = (
            plan.budget.estimated_attraction_entries
        )

        if all_attraction_costs_known:
            calculated_attraction_cost = sum(attraction_costs)

            if reported_attraction_cost is None or abs(
                reported_attraction_cost - calculated_attraction_cost
            ) > 0.01:
                findings.append(
                    ValidationFinding(
                        rule_id="ATTRACTION_BUDGET_MISMATCH",
                        severity="error",
                        message=(
                            f"Expected group attraction costs of "
                            f"{calculated_attraction_cost:.2f} CNY, "
                            f"but the reported amount is "
                            f"{reported_attraction_cost}."
                        ),
                        field_path="budget.estimated_attraction_entries",
                        suggested_correction=(
                            "Recalculate attraction costs using "
                            "per-person costs multiplied by the number of travelers."
                        )
                    )
                )

        # Check whether the reported total matches the expense categories
        expense_categories = [
            plan.budget.estimated_food,
            plan.budget.estimated_local_transport,
            plan.budget.estimated_accommodation,
            plan.budget.estimated_attraction_entries
        ]

        if all(cost is not None for cost in expense_categories):
            calculated_total = sum(expense_categories)

            if plan.budget.estimated_total is None or abs(
                plan.budget.estimated_total - calculated_total
            ) > 0.01:
                findings.append(
                    ValidationFinding(
                        rule_id="TOTAL_BUDGET_MISMATCH",
                        severity="error",
                        message=(
                            f"Expense categories total "
                            f"{calculated_total:.2f} CNY, "
                            f"but the reported total is "
                            f"{plan.budget.estimated_total}."
                        ),
                        field_path="budget.estimated_total",
                        suggested_correction=(
                            "Recalculate the total from all four expense categories."
                        )
                    )
                )
        elif plan.budget.estimated_total is not None:
            findings.append(
                ValidationFinding(
                    rule_id="INCOMPLETE_BUDGET_TOTAL",
                    severity="error",
                    message=(
                        "A total budget is reported even though "
                        "one or more expense categories are unknown."
                    ),
                    field_path="budget.estimated_total",
                    suggested_correction=(
                        "Set the total to unknown until every expense "
                        "category has a known value."
                    )
                )
            )

        # Compare the estimated group total with the requested budget
        if budget_limit_cny is not None:
            estimated_total = plan.budget.estimated_total

            if estimated_total is None:
                findings.append(
                    ValidationFinding(
                        rule_id="BUDGET_LIMIT_UNVERIFIABLE",
                        severity="warning",
                        message=(
                            "The total budget is unknown, "
                            "so compliance with the requested budget "
                            "cannot be verified."
                        ),
                        field_path="budget.estimated_total",
                        suggested_correction=(
                            "Resolve unknown expense categories "
                            "before confirming budget compliance."
                        )
                    )
                )
            elif estimated_total > budget_limit_cny:
                findings.append(
                    ValidationFinding(
                        rule_id="BUDGET_EXCEEDED",
                        severity="error",
                        message=(
                            f"Estimated group cost is {estimated_total:.2f} CNY, "
                            f"exceeding the budget of {budget_limit_cny:.2f} CNY."
                        ),
                        field_path="budget.estimated_total",
                        suggested_correction=(
                            "Reduce trip expenses while preserving "
                            "the user's important requirements."
                        )
                    )
                )

        #Report attractions that the Itinerary Agent could not schedule
        if plan.unassigned_attractions:
            findings.append(
                ValidationFinding(
                    rule_id="UNASSIGNED_ATTRACTIONS",
                    severity="warning",
                    message=(
                        f"{len(plan.unassigned_attractions)} "
                        "recommended attraction(s) were not scheduled."
                    ),
                    field_path="unassigned_attractions",
                    suggested_correction=(
                        "Review the unassigned attractions and their reasons. "
                        "Schedule suitable ones if possible."
                    )
                )
            )

        #Add qualitative AI findings without replacing Python validation.
        findings.extend(self.review_quality(plan))

        return findings
