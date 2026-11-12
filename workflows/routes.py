"""TravelMind Stage 11 route handoff. Default uses an explicitly fake fixture."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone

from providers.routing.amap import AmapRoutingClient, format_gcj02, validate_gcj02

# Synthetic test-only distances. NOT actual Xi'an travel times or routes.
SYNTHETIC = {'distance_m': 1800, 'duration_seconds': 1500, 'duration_minutes': 25}


def parse_point(text: str) -> tuple[float, float]:
    try:
        parts = text.split(',')
        if len(parts) != 2:
            raise ValueError('bad parts')
        point = (float(parts[0].strip()), float(parts[1].strip()))
    except (ValueError, TypeError):
        raise ValueError('Expected --origin and --destination as lon,lat') from None
    return validate_gcj02(point)


def build_route(*, origin: tuple[float,float], destination: tuple[float,float],
                mode: str = 'walking', live: bool = False,
                client: AmapRoutingClient | None = None) -> dict:
    # Check before any network request.
    if mode not in ('walking', 'driving'):
        raise ValueError('Mode must be walking or driving')
    start, end = validate_gcj02(origin), validate_gcj02(destination)
    if format_gcj02(start) == format_gcj02(end):
        raise ValueError('Origin and destination are identical')

    usage = {'amap_routing_requests_attempted': 0, 'open_meteo_requests_attempted': 0,
             'baidu_requests_attempted': 0, 'llm_requests_attempted': 0, 'llm_tokens': 0}
    if live:
        usage['amap_routing_requests_attempted'] = 1  # Count attempts, including API errors
        route = (client or AmapRoutingClient()).plan_route(
            origin=start, destination=end, mode=mode)
        trace = [{'step': 'amap_route_v5', 'external_requests': 1, 'mode': mode}]
        warnings = ['Route times are estimates, not a guaranteed arrival time.',
                    'The response is not a live traffic prediction for a future date.']
        output_mode = 'live_amap_transient'
    else:
        route = {
            'mode': mode,
            'origin': {'longitude': start[0], 'latitude': start[1]},
            'destination': {'longitude': end[0], 'latitude': end[1]},
            'coordinate_system': 'GCJ-02',
            'status': 'simulated_not_verified',
            **SYNTHETIC,
            'source': {'provider': 'synthetic_fixture', 'is_live': False}
        }
        trace = [{'step': 'synthetic_route_fixture', 'external_requests': 0}]
        warnings = ['SYNTHETIC FIXTURE: route distance and travel time are invented test values.']
        output_mode = 'offline_synthetic'

    return {
        'schema_version': '1.1-draft',
        'component': 'routing_adapter',
        'mode': output_mode,
        'route': route,
        'trace': trace,
        'warnings': warnings,
        'usage': usage,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description='TravelMind Stage 11 Amap walking/driving routing')
    p.add_argument('--origin', required=True, help='GCJ-02 origin longitude,latitude')
    p.add_argument('--destination', required=True, help='GCJ-02 destination longitude,latitude')
    p.add_argument('--mode', choices=['walking', 'driving'], default='walking')
    p.add_argument('--live', action='store_true', help='Explicitly authorize ONE live Amap request')
    args = p.parse_args(argv)
    try:
        result = build_route(origin=parse_point(args.origin),
                             destination=parse_point(args.destination),
                             mode=args.mode, live=args.live)
    except (ValueError, RuntimeError) as exc:
        p.exit(1, f'Error: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
