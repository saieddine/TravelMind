import unittest
from copy import deepcopy
from pydantic import BaseModel
from integration.contract_validation import audit_handoff, _evaluate, import_model


class ExampleTripRequest(BaseModel):
    city: str
    budget_cny: float


class ExampleEvidenceRecord(BaseModel):
    url: str
    field: str


class Stage16Tests(unittest.TestCase):
    def setUp(self):
        self.handoff = {
            'schema_version': 'travelmind-stage15-provisional-v1',
            'request': {'city': '西安市'},
            'field_evidence_provisional': [{'url': 'https://example.org', 'field': 'opening_hours'}],
            'usage': {'external_requests_attempted_total': 0, 'llm_tokens': 0},
        }

    def test_no_models_pending(self):
        report = audit_handoff(self.handoff)
        self.assertEqual(report['status'], 'awaiting_authoritative_models')

    def test_missing_required_reported(self):
        report = audit_handoff(self.handoff, ExampleTripRequest, ExampleEvidenceRecord)
        self.assertEqual(report['trip_request']['missing_required_fields'], ['budget_cny'])

    def test_no_network_usage(self):
        report = audit_handoff(self.handoff, ExampleTripRequest, ExampleEvidenceRecord)
        self.assertEqual(report['audit_external_requests_attempted'], 0)
        self.assertEqual(report['audit_llm_tokens'], 0)

    def test_does_not_mutate_input(self):
        original = deepcopy(self.handoff)
        audit_handoff(self.handoff, ExampleTripRequest, ExampleEvidenceRecord)
        self.assertEqual(self.handoff, original)

    def test_evidence_validated(self):
        report = audit_handoff(self.handoff, ExampleTripRequest, ExampleEvidenceRecord)
        self.assertEqual(report['evidence_record']['records_valid'], 1)

    def test_absent_evidence_not_faked(self):
        self.handoff['field_evidence_provisional'] = []
        report = audit_handoff(self.handoff, ExampleTripRequest, ExampleEvidenceRecord)
        self.assertEqual(report['evidence_record']['records_checked'], 0)
        self.assertNotEqual(report['status'], 'sample_shape_compatible_review_still_required')

    def test_unknown_fields_reported(self):
        report = _evaluate(ExampleEvidenceRecord, {'url': 'https://example.org', 'field': 'hours', 'extra': 9})
        self.assertEqual(report['unrecognized_input_fields'], ['extra'])

    def test_import_bad_format(self):
        with self.assertRaises(ValueError):
            import_model('TripRequest')

    def test_wrong_type_detected(self):
        report = _evaluate(ExampleTripRequest, {'city': 15, 'budget_cny': 100})
        self.assertFalse(report['sample_validates'])

    def test_report_does_not_expose_raw_urls(self):
        report = audit_handoff(self.handoff, ExampleTripRequest, ExampleEvidenceRecord)
        self.assertNotIn('https://example.org', str(report))


if __name__ == '__main__':
    unittest.main()
