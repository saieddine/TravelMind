"""TravelMind Stage 11: explicitly invoked Amap Route Planning 2.0 adapter.

Never calls the network during import or initialization. Live requests are
performed only by ``plan_route()``; callers gate this behind an opt-in flag.
No application-level retries, no response persistence, no LLM calls.

Amap expects GCJ-02 coordinates formatted longitude,latitude.
"""
from __future__ import annotations
from providers.config import environment_file

from datetime import datetime, timezone
from math import ceil, isfinite
from typing import Any, Callable
import os

import requests
from dotenv import load_dotenv

load_dotenv(environment_file())

ENDPOINTS = {
    'walking': 'https://restapi.amap.com/v5/direction/walking',
    'driving': 'https://restapi.amap.com/v5/direction/driving',
}


def validate_gcj02(point: tuple[float, float] | list[float]) -> tuple[float, float]:
    """Validate (lon,lat) format and broad mainland-China bounds, no transformation."""
    if not isinstance(point, (tuple, list)) or len(point) != 2:
        raise ValueError('Provide coordinates as (longitude, latitude)')
    try:
        lon, lat = float(point[0]), float(point[1])
    except (TypeError, ValueError):
        raise ValueError('Coordinates must be finite numbers') from None
    if not isfinite(lon) or not isfinite(lat):
        raise ValueError('Coordinates must be finite numbers')
    # Guard against swapped coordinates and accidental offshore/worldwide calls.
    # This geographic bounding box is only a coarse sanity check, not proof of GCJ-02.
    if not (73 <= lon <= 135 and 18 <= lat <= 54):
        raise ValueError('Coordinates appear outside mainland China or reversed')
    return lon, lat


def format_gcj02(point: tuple[float, float] | list[float]) -> str:
    lon, lat = validate_gcj02(point)
    return f'{lon:.6f},{lat:.6f}'


def _nonnegative_number(value: Any) -> float | None:
    try:
        n = float(value)
        return n if isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_route(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    """Parse one Amap v5 route. Missing cost.duration stays null."""
    if not isinstance(payload, dict) or str(payload.get('status')) != '1':
        info = payload.get('info', 'unknown error') if isinstance(payload, dict) else 'bad JSON payload'
        code = payload.get('infocode', '?') if isinstance(payload, dict) else '?'
        raise RuntimeError(f'Amap routing API rejected request: {info} ({code})')
    route = payload.get('route')
    paths = route.get('paths') if isinstance(route, dict) else None
    if not isinstance(paths, list) or not paths or not isinstance(paths[0], dict):
        return {'status': 'no_route', 'distance_m': None,
                'duration_seconds': None, 'duration_minutes': None}

    chosen = paths[0]
    distance = _nonnegative_number(chosen.get('distance'))
    # Both walking and driving v5 use show_fields=cost for duration.
    cost = chosen.get('cost') if isinstance(chosen.get('cost'), dict) else {}
    duration = _nonnegative_number(cost.get('duration'))
    # Do not infer travel time from straight-line distance; no guess.
    # Some implementations return top-level duration; only take it if present.
    if duration is None:
        duration = _nonnegative_number(chosen.get('duration'))
    return {
        'status': 'provider_route' if distance is not None else 'incomplete_route',
        'distance_m': round(distance) if distance is not None else None,
        'duration_seconds': round(duration) if duration is not None else None,
        'duration_minutes': ceil(duration / 60) if duration is not None else None,
    }


class AmapRoutingClient:
    def __init__(self, api_key: str | None = None,
                 http_get: Callable[..., Any] | None = None):
        self._api_key = api_key or os.getenv('AMAP_API_KEY')
        self._http_get = http_get or requests.get

    def plan_route(self, *, origin: tuple[float, float] | list[float],
                   destination: tuple[float, float] | list[float],
                   mode: str = 'walking') -> dict[str, Any]:
        """Perform exactly one HTTP GET after local validation."""
        if mode not in ENDPOINTS:
            raise ValueError(f'Unsupported mode {mode!r}; choose walking or driving')
        start, end = format_gcj02(origin), format_gcj02(destination)
        if start == end:
            raise ValueError('Origin and destination are the same; choose two different POIs')
        if not self._api_key:
            raise ValueError('AMAP_API_KEY not found in .env; no request made')
        endpoint = ENDPOINTS[mode]
        params = {
            'key': self._api_key,
            'origin': start,
            'destination': end,
            'show_fields': 'cost',
            'output': 'JSON',
        }
        if mode == 'driving':
            # Request one primary suggestion; no alternate routes.
            params['strategy'] = 32
        try:
            response = self._http_get(endpoint, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            # Never print request URL or params, which may contain credentials.
            raise RuntimeError(f'Amap routing connection or JSON error: {type(exc).__name__}') from None
        result = parse_route(data, mode)
        return {
            'mode': mode,
            'origin': {'longitude': float(origin[0]), 'latitude': float(origin[1])},
            'destination': {'longitude': float(destination[0]), 'latitude': float(destination[1])},
            'coordinate_system': 'GCJ-02',
            **result,
            'source': {
                'provider': 'amap',
                'endpoint': endpoint,
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'is_live': True,
            },
        }
