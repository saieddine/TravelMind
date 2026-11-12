"""Stage 16: read-only audit against authoritative teammate Pydantic models.

Does not contact providers, invoke LLMs, or change shared model definitions.
This intentionally DOES NOT invent TripRequest or EvidenceRecord schemas.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any


def import_model(spec: str):
    """Load a real model via 'python.module:ClassName'."""
    if not isinstance(spec, str) or ':' not in spec:
        raise ValueError('Use module.path:ClassName (example: backend.models:TripRequest)')
    module_name, class_name = spec.rsplit(':', 1)
    if not module_name.strip() or not class_name.isidentifier():
        raise ValueError('Invalid model import specification')
    model = getattr(import_module(module_name), class_name)
    if not hasattr(model, 'model_fields') or not hasattr(model, 'model_validate'):
        raise TypeError('Expected an importable Pydantic v2 BaseModel subclass')
    return model


def _describe(model) -> dict[str, Any]:
    required = []
    optional = []
    for name, field in model.model_fields.items():
        if field.is_required():
            required.append(name)
        else:
            optional.append(name)
    return {
        'module': model.__module__,
        'name': model.__name__,
        'required_fields': sorted(required),
        'optional_fields': sorted(optional),
        'extra_policy': str(model.model_config.get('extra', 'ignore')),
    }


def _evaluate(model, payload: dict[str, Any]) -> dict[str, Any]:
    """Conservative check: passing means only this sample validated, not full integration."""
    from pydantic import ValidationError

    if not isinstance(payload, dict):
        return {'valid': False, 'error': 'payload_must_be_object'}
    info = _describe(model)
    known = set(model.model_fields)
    present = set(payload)
    info['missing_required_fields'] = sorted(set(info['required_fields']) - present)
    info['unrecognized_input_fields'] = sorted(present - known)
    try:
        model.model_validate(payload)
        info['sample_validates'] = True
        info['validation_errors'] = []
    except ValidationError as exc:
        info['sample_validates'] = False
        info['validation_errors'] = [
            {'loc': '.'.join(map(str, e.get('loc', ()))),
             'type': e.get('type'), 'message': e.get('msg')}
            for e in exc.errors(include_input=False)[:15]
        ]
    return info


def audit_handoff(handoff: dict[str, Any], trip_model=None, evidence_model=None) -> dict[str, Any]:
    """Reports current contract differences. Does not alter the handoff object."""
    if not isinstance(handoff, dict):
        raise TypeError('handoff must be a dict')
    usage = handoff.get('usage') or {}
    response = {
        'stage': 16,
        'operation': 'read_only_contract_audit',
        'handoff_schema_version': handoff.get('schema_version'),
        'authoritative_models_provided': trip_model is not None and evidence_model is not None,
        'trip_request': None,
        'evidence_record': None,
        'evidence_count': len(handoff.get('field_evidence_provisional') or []),
        'usage_from_sample': {
            'external_requests_attempted_total': usage.get('external_requests_attempted_total', 0),
            'llm_requests_attempted': usage.get('llm_requests_attempted', 0),
            'llm_tokens': usage.get('llm_tokens', 0),
        },
        'audit_external_requests_attempted': 0,
        'audit_llm_tokens': 0,
    }
    if trip_model is None or evidence_model is None:
        response['status'] = 'awaiting_authoritative_models'
        response['next_action'] = 'Request Saieddine\'s exact Pydantic model definitions and import paths.'
        return response

    trip_payload = handoff.get('request') or {}
    evidence_payloads = handoff.get('field_evidence_provisional') or []
    if not isinstance(evidence_payloads, list):
        raise ValueError('field_evidence_provisional must be a list')
    response['trip_request'] = _evaluate(trip_model, trip_payload)
    evidence_results = [_evaluate(evidence_model, item) for item in evidence_payloads]
    response['evidence_record'] = {
        'model': _describe(evidence_model),
        'records_checked': len(evidence_results),
        'records_valid': sum(bool(item.get('sample_validates')) for item in evidence_results),
        'invalid_records': [
            {'index': i, 'missing_required_fields': item.get('missing_required_fields', []),
             'validation_errors': item.get('validation_errors', [])}
            for i, item in enumerate(evidence_results) if not item.get('sample_validates')
        ][:10],
        'sample_fields_checked': sorted(set(evidence_payloads[0])) if evidence_payloads else [],
    }
    # Lack of evidence means no real EvidenceRecord instance was validated.
    complete = bool(response['trip_request']['sample_validates']) and (
        bool(evidence_results) and all(e.get('sample_validates') for e in evidence_results)
    )
    response['status'] = ('sample_shape_compatible_review_still_required' if complete
                          else 'needs_mapping_or_real_evidence_fixture')
    response['notes'] = [
        'This is a sample-level audit, not a complete contract implementation.',
        'No field is renamed or inferred automatically; map mismatches with the team.',
        'No dummy EvidenceRecord is fabricated if sample evidence is absent.',
        'Keep unknown admission costs as null, and costs per person.',
    ]
    return response
