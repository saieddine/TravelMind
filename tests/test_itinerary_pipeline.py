from agents.itinerary_pipeline import generate_and_evaluate_itinerary
from models.attraction import AttractionInput
from models.budget import BudgetAssumptions
from agents.itinerary_agent import ItineraryAgent
from models.revision import RevisionFeedback
from models.validation import ValidationFinding


def test_pipeline_generates_and_evaluates_itinerary():
    # Create sample attractions from the Destination Agent
    attractions = [
        AttractionInput(
            id="A1",
            name_en="Forbidden City",
            name_zh="故宫",
            city_zh="北京",
            category="Historical",
            verification_status="verified",
            duration_minutes=120,
            duration_status="verified",
            estimated_cost_cny=60,
            cost_status="verified",
            selection_reason="Important historical attraction",
        ),
        AttractionInput(
            id="A2",
            name_en="Temple of Heaven",
            name_zh="天坛",
            city_zh="北京",
            category="Cultural",
            verification_status="verified",
            duration_minutes=90,
            duration_status="verified",
            estimated_cost_cny=30,
            cost_status="verified",
            selection_reason="Important cultural attraction",
        ),
    ]

    # Supply explicit assumptions so the complete budget is calculable
    assumptions = BudgetAssumptions(
        accommodation_per_room_per_night_cny=300,
        meals_per_person_per_day_cny=100,
        local_transport_per_person_per_day_cny=50,
        people_per_room=2,
    )

    # Generate the itinerary and pass it to the Critic Agent
    plan, findings = generate_and_evaluate_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=2,
        days=2,
        budget_limit_cny=2000,
        budget_assumptions=assumptions,
    )

    # Check that the Itinerary Agent generated the expected plan
    assert plan.destination == "Beijing"
    assert len(plan.days) == 2

    # Check that both attractions were scheduled
    scheduled_ids = {
        activity.attraction_id
        for day in plan.days
        for activity in day.activities
    }

    assert scheduled_ids == {"A1", "A2"}

    # Check the group attraction cost: (60 + 30) * 2
    assert plan.budget.estimated_attraction_entries == 180

    # Check that the Critic Agent found no issues
    assert findings == []

def test_itinerary_agent_accepts_revision_feedback():
    # Create a sample attraction
    attractions = [
        AttractionInput(
            id="A1",
            name_en="Forbidden City",
            name_zh="故宫",
            city_zh="北京",
            category="Historical",
            verification_status="verified",
            duration_minutes=120,
            duration_status="verified",
            estimated_cost_cny=60,
            cost_status="verified",
            selection_reason="Important historical attraction",
        )
    ]

    # Create a previous itinerary
    agent = ItineraryAgent()
    previous_plan = agent.generate_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=2,
        days=2,
    )

    # Create structured feedback from the Critic
    feedback = RevisionFeedback(
        previous_plan=previous_plan,
        findings=[
            ValidationFinding(
                rule_id="UNASSIGNED_ATTRACTIONS",
                severity="warning",
                message="Some recommended attractions were not scheduled.",
                suggested_correction="Review the daily schedule.",
            )
        ],
        revision_instructions=["Review the itinerary schedule."],
    )

    # Generate a revised itinerary
    revised_plan = agent.revise_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=2,
        days=2,
        feedback=feedback,
    )

    # Check that the revised itinerary is valid and retains the feedback
    assert revised_plan.destination == "Beijing"
    assert len(revised_plan.days) == 2
    # Check that Supervisor instructions are preserved
    assert "Review the itinerary schedule." in revised_plan.assumptions

def test_revision_repairs_duplicate_and_incorrect_totals():
    # Create two sample attractions
    attractions = [
        AttractionInput(
            id="A1",
            name_en="Forbidden City",
            name_zh="故宫",
            city_zh="北京",
            category="Historical",
            verification_status="verified",
            duration_minutes=120,
            duration_status="verified",
            estimated_cost_cny=60,
            cost_status="verified",
            selection_reason="Historical attraction",
        ),
        AttractionInput(
            id="A2",
            name_en="Summer Palace",
            name_zh="颐和园",
            city_zh="北京",
            category="Cultural",
            verification_status="verified",
            duration_minutes=90,
            duration_status="verified",
            estimated_cost_cny=30,
            cost_status="verified",
            selection_reason="Cultural attraction",
        ),
    ]

    agent = ItineraryAgent()

    # Generate an initial itinerary
    previous_plan = agent.generate_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=2,
        days=2,
    )

    # Deliberately introduce errors into the previous itinerary
    day = previous_plan.days[0]

    duplicate = day.activities[0].model_copy(deep=True)
    day.activities.append(duplicate)

    day.day_number = 7
    day.activities[0].sequence = 5
    day.total_activity_minutes = 999

    previous_plan.budget.estimated_attraction_entries = 999

    # Supply the corresponding Critic findings
    feedback = RevisionFeedback(
        previous_plan=previous_plan,
        findings=[
            ValidationFinding(
                rule_id="DUPLICATE_ATTRACTION",
                severity="error",
                message="Duplicate attraction detected.",
            ),
            ValidationFinding(
                rule_id="INCORRECT_DAY_NUMBER",
                severity="error",
                message="Incorrect day numbering.",
            ),
            ValidationFinding(
                rule_id="DAILY_DURATION_MISMATCH",
                severity="error",
                message="Daily duration is incorrect.",
            ),
            ValidationFinding(
                rule_id="ATTRACTION_BUDGET_MISMATCH",
                severity="error",
                message="Attraction budget is incorrect.",
            ),
        ],
    )

    # Apply deterministic corrections
    revised_plan = agent.revise_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=2,
        days=2,
        feedback=feedback,
    )

    revised_day = revised_plan.days[0]

    # Check that the duplicate was removed
    assert len(revised_day.activities) == 2

    # Check day numbering and activity sequences
    assert revised_day.day_number == 1
    assert [a.sequence for a in revised_day.activities] == [1, 2]

    # Check the recalculated daily duration
    assert revised_day.total_activity_minutes == 210

    # Check the recalculated group attraction cost
    assert revised_plan.budget.estimated_attraction_entries == 180

def test_revision_preserves_unresolved_findings():
    # Create an itinerary with an unknown attraction duration
    agent = ItineraryAgent()

    attractions = [
        AttractionInput(
            id="A1",
            name_en="Unknown Attraction",
            name_zh="未知景点",
            city_zh="北京",
            category="Cultural",
            verification_status="unverified",
            duration_minutes=None,
            duration_status="unknown",
            estimated_cost_cny=None,
            cost_status="unknown",
            selection_reason="Sample attraction",
        )
    ]

    previous_plan = agent.generate_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=1,
        days=1,
    )

    # Supply a finding that cannot be safely repaired automatically
    feedback = RevisionFeedback(
        previous_plan=previous_plan,
        findings=[
            ValidationFinding(
                rule_id="UNKNOWN_ACTIVITY_DURATION",
                severity="warning",
                message="Attraction duration is unknown.",
                suggested_correction="Obtain a reliable duration estimate.",
            )
        ],
    )

    revised_plan = agent.revise_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=1,
        days=1,
        feedback=feedback,
    )

    # The revision must preserve the unresolved issue
    assert any(
        "UNKNOWN_ACTIVITY_DURATION" in warning
        for warning in revised_plan.warnings
    )


def test_revision_does_not_modify_previous_plan():
    # Create a valid itinerary
    agent = ItineraryAgent()

    attractions = [
        AttractionInput(
            id="A1",
            name_en="Forbidden City",
            name_zh="故宫",
            city_zh="北京",
            category="Historical",
            verification_status="verified",
            duration_minutes=120,
            duration_status="verified",
            estimated_cost_cny=60,
            cost_status="verified",
            selection_reason="Historical attraction",
        )
    ]

    previous_plan = agent.generate_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=1,
        days=1,
    )

    # Save the original values
    original_day_number = previous_plan.days[0].day_number
    original_sequence = previous_plan.days[0].activities[0].sequence
    original_duration = previous_plan.days[0].total_activity_minutes

    # Introduce an incorrect day number
    previous_plan.days[0].day_number = 7

    feedback = RevisionFeedback(
        previous_plan=previous_plan,
        findings=[
            ValidationFinding(
                rule_id="INCORRECT_DAY_NUMBER",
                severity="error",
                message="Incorrect day number.",
            )
        ],
    )

    revised_plan = agent.revise_itinerary(
        destination="Beijing",
        attractions=attractions,
        travelers=1,
        days=1,
        feedback=feedback,
    )

    # The original plan remains unchanged by the revision
    assert previous_plan.days[0].day_number == 7

    # The revised copy contains the correction
    assert revised_plan.days[0].day_number == 1
    assert revised_plan.days[0].activities[0].sequence == original_sequence
    assert revised_plan.days[0].total_activity_minutes == original_duration