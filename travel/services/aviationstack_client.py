import logging
import os
import requests

logger = logging.getLogger(__name__)

AVIATIONSTACK_URL = 'http://api.aviationstack.com/v1'


def _resolve_api_key(api_key):
    if api_key:
        return api_key
    key = os.environ.get('AVIATIONSTACK_KEY')
    if key:
        return key
    try:
        from django.conf import settings
        key = getattr(settings, 'AVIATIONSTACK_KEY', None)
    except Exception:
        pass
    if not key:
        raise ValueError('AVIATIONSTACK_KEY nicht gesetzt (Parameter, Env-Var oder Django-Setting).')
    return key


def get_live_flights(dep_iata, arr_iata, api_key=None, limit=20):
    """
    Fetch today's scheduled/live flights between two airports.

    Free-tier note: Aviationstack free plan uses HTTP (not HTTPS) and
    allows 100 requests/month.

    Returns:
        list of dicts with flight_number, airline, departure_time,
        arrival_time, status, aircraft_type
    """
    key = _resolve_api_key(api_key)

    params = {
        'access_key': key,
        'dep_iata': dep_iata.upper(),
        'arr_iata': arr_iata.upper(),
        'limit': limit,
    }

    try:
        resp = requests.get(f'{AVIATIONSTACK_URL}/flights', params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error('Aviationstack request failed: %s', e)
        raise

    if 'error' in data:
        raise ValueError(f"Aviationstack Fehler: {data['error'].get('message', data['error'])}")

    flights = []
    for f in data.get('data', []):
        dep = f.get('departure', {})
        arr = f.get('arrival', {})
        airline = f.get('airline', {})
        flight = f.get('flight', {})
        aircraft = f.get('aircraft', {}) or {}

        flights.append({
            'flight_number': flight.get('iata') or flight.get('icao', ''),
            'airline_name': airline.get('name', ''),
            'airline_iata': airline.get('iata', ''),
            'departure_scheduled': dep.get('scheduled', ''),
            'departure_actual': dep.get('actual') or dep.get('estimated', ''),
            'arrival_scheduled': arr.get('scheduled', ''),
            'arrival_actual': arr.get('actual') or arr.get('estimated', ''),
            'status': f.get('flight_status', ''),
            'aircraft_type': aircraft.get('iata', '') or aircraft.get('icao', ''),
        })

    return flights


def account_status(api_key=None):
    """Check remaining Aviationstack API calls (does not consume quota)."""
    key = _resolve_api_key(api_key)
    try:
        resp = requests.get(
            f'{AVIATIONSTACK_URL}/flights',
            params={'access_key': key, 'limit': 1},
            timeout=10,
        )
        data = resp.json()
    except requests.RequestException as e:
        logger.error('Aviationstack status check failed: %s', e)
        raise

    pagination = data.get('pagination', {})
    return {
        'total_results': pagination.get('total'),
        'error': data.get('error'),
    }
