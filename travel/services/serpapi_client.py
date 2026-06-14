import logging
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

SERPAPI_URL = 'https://serpapi.com/search'


def _resolve_api_key(api_key):
    """Return api_key if given, else fall back to env var, then Django settings."""
    if api_key:
        return api_key
    key = os.environ.get('SERPAPI_KEY')
    if key:
        return key
    try:
        from django.conf import settings
        key = getattr(settings, 'SERPAPI_KEY', None)
    except Exception:
        pass
    if not key:
        raise ValueError('SERPAPI_KEY nicht gesetzt (Parameter, Env-Var oder Django-Setting).')
    return key


def account_status(api_key=None):
    """Fetch SerpAPI account usage — does NOT count toward monthly quota."""
    key = _resolve_api_key(api_key)
    try:
        resp = requests.get(
            'https://serpapi.com/account.json',
            params={'api_key': key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error('SerpAPI account status request failed: %s', e)
        raise

    return {
        'plan_name': data.get('plan_name'),
        'plan_searches_left': data.get('plan_searches_left'),
        'plan_monthly_price': data.get('plan_monthly_price'),
        'searches_per_month': data.get('searches_per_month'),
        'this_month_usage': data.get('this_month_usage'),
        'account_email': data.get('account_email'),
        'extra_credits': data.get('extra_credits', 0),
        'last_hour_searches': data.get('searches_per_time_period', 0),
    }


def search_flights(
    departure_id,
    arrival_id,
    outbound_date,
    return_date=None,
    adults=1,
    travel_class='1',
    direct_only=False,
    currency='EUR',
    auto_fetch_return=3,
    api_key=None,
):
    api_key = _resolve_api_key(api_key)

    params = {
        'engine': 'google_flights',
        'departure_id': departure_id,
        'arrival_id': arrival_id,
        'outbound_date': outbound_date.strftime('%Y-%m-%d'),
        'adults': adults,
        'travel_class': travel_class,
        'currency': currency,
        'hl': 'de',
        'gl': 'de',
        'api_key': api_key,
    }

    is_roundtrip = bool(return_date)
    if return_date:
        params['return_date'] = return_date.strftime('%Y-%m-%d')
    else:
        params['type'] = '2'  # one-way

    if direct_only:
        params['stops'] = '1'

    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error('SerpAPI request failed: %s', e)
        raise

    if 'error' in data:
        raise ValueError(f"SerpAPI Fehler: {data['error']}")

    flights = _parse_outbound(data, is_roundtrip)

    # Sort by price ascending (None prices go last)
    flights.sort(key=lambda f: f['price'] if f['price'] is not None else 999999)

    # Eagerly fetch return flights for the top N results in parallel
    if is_roundtrip and auto_fetch_return > 0:
        top = [f for f in flights[:auto_fetch_return] if f.get('departure_token')]
        if top:
            _fetch_return_flights_parallel(top, api_key, params)

    from urllib.parse import urlencode
    base_qs = urlencode({k: v for k, v in params.items() if k != 'api_key'})

    return {
        'flights': flights,
        'is_roundtrip': is_roundtrip,
        'base_qs': base_qs,
        'price_insights': data.get('price_insights', {}),
    }


def fetch_return_flights(departure_token, base_params, api_key=None):
    """Second-step call: fetch return flight options for a given departure_token.

    base_params must contain the original search parameters (departure_id,
    arrival_id, outbound_date, return_date, adults, travel_class, …) because
    SerpAPI requires them alongside the departure_token.
    """
    api_key = _resolve_api_key(api_key)
    params = {**base_params, 'departure_token': departure_token, 'api_key': api_key}
    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error('SerpAPI return-flights request failed: %s', e)
        raise

    if 'error' in data:
        raise ValueError(f"SerpAPI Fehler: {data['error']}")

    return_legs = []
    for section in ('best_flights', 'other_flights'):
        for item in data.get(section, []):
            return_legs.append({
                'price': item.get('price'),
                'total_duration': item.get('total_duration'),
                'legs': [_parse_leg(l) for l in item.get('flights', [])],
            })
    return return_legs


def _fetch_return_flights_parallel(flights_list, api_key, base_params):  # api_key already resolved
    """Fetch return flights for multiple outbound results concurrently."""
    def fetch_one(flight):
        try:
            flight['return_options'] = fetch_return_flights(
                flight['departure_token'], base_params)
        except Exception as e:
            logger.warning('Return-flight fetch failed for token %s: %s',
                           flight.get('departure_token'), e)
            flight['return_options'] = []

    with ThreadPoolExecutor(max_workers=len(flights_list)) as ex:
        futures = [ex.submit(fetch_one, f) for f in flights_list]
        for fut in as_completed(futures):
            fut.result()  # re-raises if fetch_one raised


def _parse_leg(leg):
    dep = leg.get('departure_airport', {})
    arr = leg.get('arrival_airport', {})
    return {
        'airline': leg.get('airline'),
        'airline_logo': leg.get('airline_logo'),
        'flight_number': leg.get('flight_number'),
        'departure_airport': dep.get('id'),
        'departure_airport_name': dep.get('name', ''),
        'departure_time': dep.get('time'),
        'arrival_airport': arr.get('id'),
        'arrival_airport_name': arr.get('name', ''),
        'arrival_time': arr.get('time'),
        'duration': leg.get('duration'),
        'airplane': leg.get('airplane'),
        'overnight': leg.get('overnight', False),
    }


def _parse_outbound(data, is_roundtrip):
    flights = []
    for section in ('best_flights', 'other_flights'):
        for item in data.get(section, []):
            flights.append({
                'is_best': section == 'best_flights',
                'price': item.get('price'),
                'total_duration': item.get('total_duration'),
                'carbon_emissions': item.get('carbon_emissions', {}).get('this_flight'),
                'departure_token': item.get('departure_token') if is_roundtrip else None,
                'outbound_legs': [_parse_leg(l) for l in item.get('flights', [])],
                'return_options': None,  # filled later for top results
            })
    return flights
