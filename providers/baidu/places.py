"""Optional Baidu Maps Place Search 3.0 fallback. One request, no retries.

Docs: https://lbsyun.baidu.com/docs/webapi?title=placev3/guide/webservice-placeapiV3/interfaceDocumentV3
Use only with an authorized Baidu browser/server key and appropriate data terms.
"""
from __future__ import annotations
from providers.config import environment_file

import os
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

from providers.amap.poi_v5 import clean

load_dotenv(environment_file())

URL = 'https://api.map.baidu.com/place/v3/region'


def baidu_poi_to_place(poi: dict, city: str, timestamp: str) -> dict:
    details = poi.get('detail_info')
    if not isinstance(details, dict):
        details = {}
    hours = clean(details.get('shop_hours'))
    coord = poi.get('location') if isinstance(poi.get('location'), dict) else {}
    try:
        lon, lat = float(coord['lng']), float(coord['lat'])
        coordinates = {'longitude': lon, 'latitude': lat, 'system': 'GCJ-02'}
    except (KeyError, ValueError, TypeError):
        coordinates = None
    url = clean(details.get('detail_url'))
    if url and not url.startswith('https://'):
        url = None
    return {
        'attraction_id': clean(poi.get('uid')),
        'name_zh': clean(poi.get('name')),
        'name_en': None,
        'city_zh': clean(poi.get('city')) or city,
        'category': clean(details.get('classified_poi_tag')),
        'tags': [],
        'address_zh': clean(poi.get('address')),
        'coordinates': coordinates,
        'location': {'latitude': coordinates['latitude'], 'longitude': coordinates['longitude']}
                    if coordinates else None,
        'opening_hours': hours,
        'opening_hours_today': None,
        'opening_hours_status': 'provider_reported_unverified' if hours else 'unknown',
        'ticket_price_cny': None,
        'provider_price_raw': clean(details.get('price')),  # NOT necessarily an entry ticket
        'rating_raw': clean(details.get('overall_rating')),
        'duration_minutes': None,
        'duration_status': 'unknown',
        'estimated_cost_cny': None,
        'cost_status': 'unknown',
        'cost_basis': 'per_person',
        'selection_reason': 'Exact named-place Baidu search; itinerary suitability unverified',
        'source': {'provider': 'baidu_maps', 'provider_poi_id': clean(poi.get('uid')),
                   'url': url, 'retrieved_at': timestamp, 'role': 'poi_search_v3'},
        'field_provenance': ({'opening_hours': [{'provider': 'baidu_maps',
                                                 'retrieved_at': timestamp,
                                                 'scope': 'unverified_business_hours'}]}
                             if hours else {}),
        'verification_status': 'provider_reported_unverified_details',
    }


class BaiduPlacesClient:
    def __init__(self, key: str | None = None, http_get=None):
        self.key = key or os.getenv('BAIDU_MAP_AK')
        if not self.key:
            raise ValueError('BAIDU_MAP_AK missing; do not enable --baidu until you obtain one')
        self.http_get = http_get or requests.get

    def search_named(self, *, city: str, keyword: str) -> list[dict]:
        if not isinstance(keyword, str) or not 1 <= len(keyword.strip()) <= 80:
            raise ValueError('Baidu fallback requires one exact place name (1..80 characters)')
        if not city:
            raise ValueError('City required')
        params = {'ak': self.key, 'query': keyword, 'region': city,
                  'region_limit': 'true', 'scope': 2, 'page_num': 0,
                  'page_size': 10, 'ret_coordtype': 'gcj02ll',
                  'photo_show': 'false', 'output': 'json'}
        try:
            response = self.http_get(URL, params=params, timeout=12)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError('Baidu HTTPS/JSON request failed (check network, key, permissions)') from None
        if not isinstance(payload, dict) or payload.get('status') != 0:
            status = payload.get('status') if isinstance(payload, dict) else 'invalid_response'
            raise RuntimeError(f'Baidu returned status={status}; check console quota/permissions')
        rows = payload.get('results')
        now = datetime.now(timezone.utc).isoformat()
        return [baidu_poi_to_place(p, city, now) for p in rows[:10] if isinstance(p, dict)] \
               if isinstance(rows, list) else []
