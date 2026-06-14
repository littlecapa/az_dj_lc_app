"""
OpenFlights offline route database.

Data: https://github.com/jpatokal/openflights
routes.dat columns:
  0  Airline IATA/ICAO
  1  Airline ID
  2  Source airport IATA
  3  Source airport ID
  4  Destination airport IATA
  5  Destination airport ID
  6  Codeshare flag
  7  Stops (0 = direct)
  8  Equipment (aircraft codes)

airlines.dat columns:
  0  Airline ID
  1  Name
  2  Alias
  3  IATA
  4  ICAO
  5  Callsign
  6  Country
  7  Active (Y/N)
"""

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / 'data'

# --- Module-level caches (loaded once at import) ---

def _load_airlines():
    airlines = {}
    path = _DATA_DIR / 'airlines.dat'
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            iata = row[3].strip()
            if iata and iata != r'\N' and iata != '-':
                airlines[iata] = {
                    'name': row[1].strip(),
                    'country': row[6].strip(),
                    'active': row[7].strip() == 'Y',
                }
    return airlines


def _load_routes():
    routes = {}  # (dep_iata, arr_iata) → list of airline_iata codes
    path = _DATA_DIR / 'routes.dat'
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            airline = row[0].strip()
            dep = row[2].strip()
            arr = row[4].strip()
            stops = row[7].strip()
            equipment = row[8].strip() if len(row) > 8 else ''

            if not airline or not dep or not arr:
                continue
            if r'\N' in (airline, dep, arr):
                continue

            key = (dep, arr)
            if key not in routes:
                routes[key] = []
            routes[key].append({
                'airline_iata': airline,
                'stops': int(stops) if stops.isdigit() else 0,
                'equipment': [e.strip() for e in equipment.split()] if equipment else [],
            })
    return routes


_AIRLINES = _load_airlines()
_ROUTES = _load_routes()
logger.info('OpenFlights loaded: %d airlines, %d route pairs', len(_AIRLINES), len(_ROUTES))


def search_routes(dep_iata, arr_iata, direct_only=True):
    """
    Return airlines operating between dep_iata and arr_iata.

    Args:
        dep_iata:    Departure airport IATA code (e.g. 'FRA')
        arr_iata:    Arrival airport IATA code (e.g. 'BKK')
        direct_only: If True, only return non-stop routes (stops == 0)

    Returns:
        list of dicts:
            airline_iata, airline_name, country, active, equipment, stops
    """
    dep = dep_iata.upper()
    arr = arr_iata.upper()

    raw = _ROUTES.get((dep, arr), [])

    results = []
    seen = set()

    for entry in raw:
        if direct_only and entry['stops'] > 0:
            continue
        code = entry['airline_iata']
        if code in seen:
            continue
        seen.add(code)

        airline_info = _AIRLINES.get(code, {})
        results.append({
            'airline_iata': code,
            'airline_name': airline_info.get('name', code),
            'country': airline_info.get('country', ''),
            'active': airline_info.get('active', True),
            'equipment': entry['equipment'],
            'stops': entry['stops'],
        })

    results.sort(key=lambda r: (not r['active'], r['airline_name']))
    return results
