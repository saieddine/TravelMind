"""Amap POI Search 2.0: one opt-in HTTP request, no persistence or LLM.

Official documentation: https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch
Provider data is transient. Do not redistribute or cache without authorization.
"""
from __future__ import annotations
from providers.config import environment_file

import os
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(environment_file())

URL = 'https://restapi.amap.com/v5/place/text'
# Query deliberately bounded to one city, one page and at most 10 results.
CATEGORIES = {
    'museum': '博物馆',
    'attraction': '旅游景点',
    'restaurant': '餐厅',
    'hotel': '酒店',
}


def clean(value: Any) -> str | None:
    """Amap sometimes uses [] or '' rather than null for missing fields."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def gcj02(location: Any) -> dict | None:
    if not isinstance(location, str):
        return None
    try:
        longitude, latitude = (float(v) for v in location.split(','))
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            return None
        return {'longitude': longitude, 'latitude': latitude, 'system': 'GCJ-02'}
    except (TypeError, ValueError):
        return None


def amap_poi_to_place(poi: dict, city: str, retrieved_at: str) -> dict:
    business = poi.get('business')
    if not isinstance(business, dict):
        business = {}
    weekly = clean(business.get('opentime_week'))
    today = clean(business.get('opentime_today'))
    average_spend = clean(business.get('cost'))
    coords = gcj02(poi.get('location'))
    source = {'provider': 'amap', 'provider_poi_id': clean(poi.get('id')),
              'url': None, 'retrieved_at': retrieved_at, 'role': 'poi_search_v5'}
    evidence = {}
    if clean(poi.get('address')):
        evidence['address_zh'] = [{'provider': 'amap', 'retrieved_at': retrieved_at}]
    if coords:
        evidence['coordinates'] = [{'provider': 'amap', 'retrieved_at': retrieved_at}]
    if weekly:
        evidence['opening_hours'] = [{'provider': 'amap', 'retrieved_at': retrieved_at,
                                      'scope': 'general_weekly_description'}]
    if today:
        evidence['opening_hours_today'] = [{'provider': 'amap', 'retrieved_at': retrieved_at,
                                            'scope': 'today_only_not_future_travel_date'}]
    return {
        'attraction_id': clean(poi.get('id')),
        'name_zh': clean(poi.get('name')),
        'name_en': None,
        'city_zh': clean(poi.get('cityname')) or city,
        'district_zh': clean(poi.get('adname')),
        'category': clean(poi.get('type')),
        'tags': [],
        'address_zh': clean(poi.get('address')),
        'coordinates': coords,
        'location': {'latitude': coords['latitude'], 'longitude': coords['longitude']}
                    if coords else None,
        'opening_hours': weekly,
        'opening_hours_today': today,
        'opening_hours_status': 'provider_weekly_unverified' if weekly else
                                'today_only_not_future_schedule' if today else 'unknown',
        'ticket_price_cny': None,
        'average_spend_raw': average_spend,  # NOT an admission price
        'rating_raw': clean(business.get('rating')),
        'duration_minutes': None,
        'duration_status': 'unknown',
        'estimated_cost_cny': None,
        'cost_status': 'unknown',
        'cost_basis': 'per_person',
        'selection_reason': 'Matched selected city and search query; needs itinerary review',
        'source': source,
        'field_provenance': evidence,
        'verification_status': 'provider_reported_unverified_details',
    }


class AmapV5Client:
    def __init__(self, key: str | None = None, http_get=None):
        self.key = key or os.getenv('AMAP_API_KEY')
        if not self.key:
            raise ValueError('AMAP_API_KEY missing; put it in .env (do not share it)')
        self.http_get = http_get or requests.get

    def search(self, *, city: str, keyword: str | None = None,
               category: str = 'attraction', limit: int = 5) -> list[dict]:
        if category not in CATEGORIES:
            raise ValueError('Unsupported category')
        if not isinstance(city, str) or not city.strip():
            raise ValueError('A Chinese city is required')
        if not 1 <= limit <= 10:
            raise ValueError('This prototype limits each search to 1..10 records')
        if keyword is not None and (not keyword.strip() or len(keyword) > 80):
            raise ValueError('Keyword must be 1..80 characters')
        query = keyword or CATEGORIES[category]
        params = {'key': self.key, 'keywords': query, 'region': city,
                  'city_limit': 'true', 'show_fields': 'business',
                  'page_size': limit, 'page_num': 1, 'output': 'json'}
        try:
            response = self.http_get(URL, params=params, timeout=12)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError('Amap HTTPS/JSON request failed (check network, key, permissions)') from None
        if not isinstance(payload, dict) or str(payload.get('status')) != '1':
            info = payload.get('info') if isinstance(payload, dict) else 'invalid_response'
            code = payload.get('infocode') if isinstance(payload, dict) else '?'
            raise RuntimeError(f'Amap reported {info} ({code}); check your console quota/permissions')
        now = datetime.now(timezone.utc).isoformat()
        pois = payload.get('pois')
        if not isinstance(pois, list):
            return []
        return [amap_poi_to_place(p, city, now) for p in pois[:limit] if isinstance(p, dict)]
