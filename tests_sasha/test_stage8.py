import unittest
from copy import deepcopy
from data.poi_quality import filter_candidates
from integration.candidate_handoff import provisional_itinerary_handoff

class TestStage8(unittest.TestCase):
    def sample(self):
        return {
            'request': {'keyword':'陕西历史博物馆', 'city':'西安市'},
            'places': [
                {'name_zh':'陕西历史博物馆', 'attraction_id':'M', 'ticket_price_cny':0,
                 'estimated_cost_cny':0,'cost_status':'official_admission_reference_check_eligibility',
                 'field_provenance':{'ticket_price_cny':[{'provider':'official_attraction_website'}]}},
                {'name_zh':'陕西历史博物馆停车场(出入口)','attraction_id':'P1'},
                {'name_zh':'陕西历史博物馆停车场','attraction_id':'P2'},
            ],
            'usage': {'amap_v5_requests_attempted':1, 'llm_tokens':0},
        }
    def test_only_museum(self):
        out=filter_candidates(self.sample())
        self.assertEqual(len(out['places']),1)
        self.assertEqual(out['quality']['returned_before_filtering'],3)
        self.assertEqual(len(out['quality']['excluded']),2)
    def test_preserves_usage_and_input(self):
        before=self.sample(); snapshot=deepcopy(before)
        out=filter_candidates(before)
        self.assertEqual(before,snapshot)
        self.assertEqual(out['usage'],snapshot['usage'])
    def test_zero_is_valid_with_evidence(self):
        out=filter_candidates(self.sample())
        handoff=provisional_itinerary_handoff(out)
        self.assertEqual(handoff['places'][0]['estimated_cost_cny'],0)
    def test_generic_discovery(self):
        before=self.sample();before['request']['keyword']=None
        out=filter_candidates(before)
        self.assertEqual(len(out['places']),1)
    def test_no_exact_match(self):
        before=self.sample();before['request']['keyword']='西安碑林博物馆'
        out=filter_candidates(before)
        self.assertEqual(out['places'],[])
        self.assertTrue(out['warnings'])

if __name__=='__main__': unittest.main()
