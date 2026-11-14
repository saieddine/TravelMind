
from typing import Any

from models.attraction import AttractionInput
from models.itinerary import ItineraryPlan
from models.validation import ValidationFinding


# These are the verification statuses supported by the team contract.
VALID_EVIDENCE_STATUSES = {
    "verified_live",
    "curated_sample",
    "unverified",
    "not_applicable",
}


def _create_evidence(attractions: list[AttractionInput]) -> list[dict[str, Any]]:
    """Convert attraction source metadata into shared evidence records."""

    evidence = []

    for attraction in attractions:
        # Include the primary source and any additional source records.
        source_records = [attraction.source, *attraction.sources]

        for source_record in source_records:
            if not source_record:
                continue

            # Preserve an explicit source type when it matches the contract.
            source_type = source_record.get("source_type", "other")
            if source_type not in {
                "local_dataset", "external_api", "user_input",
                "llm_output", "other",
            }:
                source_type = "other"

            # Preserve supported verification statuses.
            verification_status = source_record.get(
                "verification_status",
                attraction.verification_status,
            )
            if verification_status not in VALID_EVIDENCE_STATUSES:
                verification_status = "unverified"

            # Build a readable source reference without inventing a URL.
            source_name = (
                source_record.get("url")
                or source_record.get("provider")
                or source_record.get("source")
                or attraction.id
            )

            evidence.append({
                "source": str(source_name),
                "source_type": source_type,
                "verification_status": verification_status,
                "observed_at": source_record.get("observed_at"),
                "notes": (
                    f"Evidence for attraction {attraction.id}: "
                    f"{attraction.name_en}"
                ),
            })

    return evidence


def build_itinerary_agent_result(
    plan: ItineraryPlan,
    findings: list[ValidationFinding],
    attractions: list[AttractionInput],
) -> dict[str, Any]:
    """
    Package the itinerary and critic findings in the team's
    agreed AgentResult structure.

    The actual shared AgentResult model can validate this payload
    when the team integrates its workflow module.
    """

    # Separate errors and warnings for the Supervisor.
    errors = [
        finding.message
        for finding in findings
        if finding.severity == "error"
    ]

    warnings = [
        finding.message
        for finding in findings
        if finding.severity == "warning"
    ]

    # Determine whether the proposed itinerary needs revision.
    if errors:
        status = "needs_revision"
        next_action = "revise_itinerary"
    elif warnings or plan.warnings:
        status = "partial"
        next_action = None
    else:
        status = "success"
        next_action = None

    return {
        "agent_name": "itinerary_agent",
        "status": status,
        "data": {
            "itinerary": plan.model_dump(mode="json"),
            "validation_findings": [
                finding.model_dump(mode="json")
                for finding in findings
            ],
        },
        "evidence": _create_evidence(attractions),
        "warnings": warnings + plan.warnings,
        "errors": errors,
        "next_action": next_action,
    }
