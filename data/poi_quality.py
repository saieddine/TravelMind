"""Free deterministic POI filtering. No network calls, no LLM tokens."""
from copy import deepcopy
from data.provider_router import same_place_name

ANCILLARY_TERMS = (
    '停车场', '停车位', '停车楼', '出入口', '售票处',
    '售票窗口', '卫生间', '公共厕所', '充电桩',
)

def filter_candidates(result, keyword=None):
    """Return provider result with non-destination POIs removed.

    A named-place search requires an exact Chinese name match.
    Generic search removes clearly ancillary POIs and exact duplicates.
    """
    out = deepcopy(result)
    candidates = out.get('places') or []
    target = keyword or (out.get('request') or {}).get('keyword')
    kept, excluded, seen = [], [], set()
    for p in candidates:
        name = p.get('name_zh') or p.get('name_en') or ''
        reason = None
        if any(term in name for term in ANCILLARY_TERMS):
            reason = 'ancillary_location'
        elif target and not same_place_name(name, target):
            reason = 'not_exact_name_match'
        poi_id = p.get('attraction_id') or p.get('id') or (p.get('source') or {}).get('provider_poi_id')
        key = ('id', str(poi_id)) if poi_id else ('name', name.strip().casefold())
        if reason is None and key in seen:
            reason = 'duplicate'
        if reason:
            excluded.append({'name': name, 'reason': reason})
            continue
        seen.add(key)
        kept.append(p)
    out['places'] = kept
    out['quality'] = {
        'returned_before_filtering': len(candidates),
        'attractions_after_filtering': len(kept),
        'excluded': excluded,
        'exact_name_requested': target,
    }
    out.setdefault('trace', []).append({'step': 'poi_quality_gate', 'external_calls': 0})
    if target and not kept:
        out.setdefault('warnings', []).append('No exact attraction name match; related POIs excluded.')
    return out
