"""Stage 6 cost-gated multi-provider POI retrieval for TravelMind.

Offline mode: Stage 5 local enrichment, zero network and zero LLM tokens.
Live mode: at most one Amap v5 place search, plus ONE optional Baidu v3
fallback for a specific named attraction with missing opening hours.
Neither live provider's responses are written to disk.
"""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from typing import Any

from data.enrichment import enrich_places
from agents.destination_agent import understand_locally
from workflows.enrichment import run as run_stage5_offline
from providers.amap.poi_v5 import AmapV5Client
from providers.baidu.places import BaiduPlacesClient


def same_place_name(a: str | None, b: str | None) -> bool:
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    normalize = lambda s: re.sub(r'[\s\-()（）【】·•]', '', s).casefold()
    return bool(normalize(a)) and normalize(a) == normalize(b)


def add_contract_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Provisional handoff fields requested by Itinerary teammate.

    estimated_cost_cny is a *per-person reference admission cost* only if
    an independently sourced ticket price exists. Never use provider average
    spend as an admission price, and never turn unknown into zero.
    """
    place = deepcopy(item)
    place.setdefault('duration_minutes', None)
    place.setdefault('duration_status', 'unknown')
    place.setdefault('estimated_cost_cny', None)
    place.setdefault('cost_status', 'unknown')
    place.setdefault('cost_basis', 'per_person')
    place.setdefault('selection_reason', 'Matches requested destination/interests; itinerary agent must schedule')
    coords = place.get('coordinates')
    if 'location' not in place:
        place['location'] = ({'latitude': coords['latitude'], 'longitude': coords['longitude']}
                             if isinstance(coords, dict) and 'latitude' in coords and 'longitude' in coords
                             else None)
    price = place.get('ticket_price_cny')
    provenance = place.get('field_provenance') or {}
    if price is not None and 'ticket_price_cny' in provenance:
        place['estimated_cost_cny'] = price
        place['cost_status'] = 'official_admission_reference_check_eligibility'
        place['cost_basis'] = 'per_person'
    return place


def _named_match(places: list[dict], keyword: str, city: str):
    for item in places:
        if (same_place_name(item.get('name_zh'), keyword)
                and item.get('city_zh') == city):
            return item
    return None


def select_baidu_alternative(target: dict | None, candidate: dict) -> dict:
    """Choose a complete Baidu record rather than blending two map databases.

    Amap and Baidu have separate terms and provenance. Never transplant a
    Baidu field into an Amap POI (or vice versa) without a reviewed license.
    """
    if target and not candidate.get('opening_hours'):
        return target  # replacement would not add the missing information
    selected = deepcopy(candidate)
    selected['provider_selection_reason'] = (
        'Opt-in Baidu named-place alternative when Amap lacked general hours'
        if target else 'Opt-in Baidu named-place fallback when Amap did not identify the place'
    )
    return selected


def run_provider_search(text: str, *, city: str | None = None, keyword: str | None = None,
                        category: str = 'attraction', limit: int = 5,
                        travel_date: str | None = None, live_amap: bool = False,
                        with_baidu: bool = False,
                        amap_client=None, baidu_client=None) -> dict:
    # Validate all user input BEFORE any potentially quota-consuming request.
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Travel request text required')
    if category not in {'museum', 'attraction', 'restaurant', 'hotel'}:
        raise ValueError('category must be museum, attraction, restaurant or hotel')
    if not 1 <= limit <= 10:
        raise ValueError('limit must be 1..10')
    if keyword is not None and (not 1 <= len(keyword.strip()) <= 80):
        raise ValueError('keyword must be 1..80 characters')
    if travel_date is not None:
        date.fromisoformat(travel_date)
    if with_baidu and (not live_amap or not keyword):
        raise ValueError('Baidu fallback requires BOTH --live-amap and --keyword')

    parsed = understand_locally(text, city=city)
    selected_city = parsed['city']
    if not live_amap:
        output = run_stage5_offline(text, city=selected_city,
                                    limit=limit, travel_date=travel_date, live=False)
        output['schema_version'] = '1.3-provisional'
        output['places'] = [add_contract_fields(p) for p in output['places']]
        output['usage'].update({'amap_v5_requests_attempted': 0,
                                'baidu_v3_requests_attempted': 0,
                                'llm_requests_attempted': 0, 'llm_tokens': 0})
        output['warnings'].append('Stage 6 is OFFLINE; no Amap/Baidu requests or LLM calls.')
        return output

    # Require credentials before the first external call; don't waste an Amap
    # request discovering Baidu credentials are absent.
    amap_client = amap_client if amap_client is not None else AmapV5Client()
    if with_baidu:
        baidu_client = baidu_client if baidu_client is not None else BaiduPlacesClient()
    usage = {'amap_v5_requests_attempted': 0, 'baidu_v3_requests_attempted': 0,
             'llm_requests_attempted': 0, 'llm_tokens': 0}
    trace: list[dict] = []
    warnings: list[str] = list(parsed['warnings'])
    places: list[dict] = []
    try:
        usage['amap_v5_requests_attempted'] = 1
        trace.append({'step': 'amap_v5_place_search', 'calls': 1,
                      'query': keyword or category, 'city': selected_city})
        places = amap_client.search(city=selected_city, keyword=keyword,
                                    category=category, limit=limit)
    except RuntimeError as exc:
        if not with_baidu:
            raise
        warnings.append(f'Amap search failed; explicitly enabled Baidu fallback may be used: {exc}')

    places, enrichment = enrich_places(places, travel_date=travel_date)
    target = _named_match(places, keyword, selected_city) if keyword else None
    # Amap's "opentime_today" alone is not a weekly or future-date schedule.
    if with_baidu and (target is None or not target.get('opening_hours')):
        usage['baidu_v3_requests_attempted'] = 1
        trace.append({'step': 'baidu_v3_named_fallback', 'calls': 1,
                      'query': keyword, 'city': selected_city,
                      'reason': 'exact named attraction missing general hours'})
        candidates = baidu_client.search_named(city=selected_city, keyword=keyword)
        exact = _named_match(candidates, keyword, selected_city)
        if exact is None:
            warnings.append('Baidu returned no exact same-city name match; did not combine records.')
        else:
            selected = select_baidu_alternative(target, exact)
            if target is not None and selected is not target:
                # Complete-provider substitution, NOT field-level blending.
                places = [selected if item is target else item for item in places]
                warnings.append('Selected a complete Baidu record instead of merging map-provider fields.')
            elif target is None:
                warnings.append('Only Baidu found an exact same-city name; kept as separate POI identity.')
                places = ([selected] + places)[:limit]
            else:
                warnings.append('Baidu returned no additional general hours; retained the Amap record.')
    elif with_baidu:
        trace.append({'step': 'baidu_skipped', 'calls': 0,
                      'reason': 'general hours already present after Amap/official data'})

    output = {
        'schema_version': '1.3-provisional',
        'agent': 'destination_agent',
        'mode': 'live_provider_transient',
        'request': {'text': text, 'city': selected_city, 'keyword': keyword,
                    'category': category, 'travel_date': travel_date},
        'places': [add_contract_fields(p) for p in places],
        'enrichment': enrichment,
        'usage': usage,
        'trace': trace + [{'step': 'handoff', 'target': 'itinerary_agent',
                           'place_count': len(places)}],
        'warnings': warnings + [
            'Provider business hours are not proof of future-date holiday hours or ticket availability.',
            'Amap cost and Baidu price are not automatically admission ticket prices.',
            'Live POI data is transient; do not export/store it without appropriate provider permission.',
            'Map provider records are never blended: Baidu is a complete-provider alternative.',
        ],
    }
    return output
