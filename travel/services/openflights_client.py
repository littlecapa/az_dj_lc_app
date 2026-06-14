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
    """
    Build two lookups:
      - by_id[airline_id]   → airline dict  (used when routes.dat has numeric IDs)
      - by_iata[iata_code]  → airline dict  (prefer the entry whose name does NOT
                               contain 'Cargo', 'Technik', 'Systems', 'CityLine'
                               so that e.g. LH resolves to Lufthansa, not Lufthansa Cargo)
    """
    by_id = {}
    by_iata_candidates = {}  # iata → list of dicts

    path = _DATA_DIR / 'airlines.dat'
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            airline_id = row[0].strip()
            iata = row[3].strip()
            if not iata or iata in (r'\N', '-'):
                iata = None
            entry = {
                'name': row[1].strip(),
                'country': row[6].strip(),
                'active': row[7].strip() == 'Y',
            }
            if airline_id.lstrip('-').isdigit():
                by_id[airline_id] = entry
            if iata:
                by_iata_candidates.setdefault(iata, []).append(entry)

    # For each IATA code with multiple candidates, prefer the "main" carrier
    _subsidiary_keywords = ('cargo', 'technik', 'systems', 'cityline', 'express',
                            'regional', 'connect', 'link', 'shuttle')
    by_iata = {}
    for iata, candidates in by_iata_candidates.items():
        main = [c for c in candidates
                if not any(kw in c['name'].lower() for kw in _subsidiary_keywords)]
        by_iata[iata] = (main or candidates)[0]

    return by_id, by_iata


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

            codeshare = row[6].strip() == 'Y'
            key = (dep, arr)
            if key not in routes:
                routes[key] = []
            routes[key].append({
                'airline_iata': airline,
                'codeshare': codeshare,
                'stops': int(stops) if stops.isdigit() else 0,
                'equipment': [e.strip() for e in equipment.split()] if equipment else [],
            })
    return routes


_AIRLINES_BY_ID, _AIRLINES_BY_IATA = _load_airlines()
_ROUTES = _load_routes()
logger.info('OpenFlights loaded: %d airlines, %d route pairs',
            len(_AIRLINES_BY_IATA), len(_ROUTES))


def search_routes(dep_iata, arr_iata, direct_only=True):
    """
    Return operated routes between dep_iata and arr_iata with codeshares resolved.

    Codeshare entries (flag Y) are NOT shown as separate rows — they are collected
    and attached to the operating airline's entry as `codeshare_codes`.

    Returns:
        list of dicts:
            airline_iata, airline_name, country, active, equipment, stops,
            codeshare_codes (list of IATA codes that market this flight)
    """
    dep = dep_iata.upper()
    arr = arr_iata.upper()

    raw = _ROUTES.get((dep, arr), [])

    operators = {}   # iata → entry dict
    codeshares = []  # iata codes that are pure codeshares

    for entry in raw:
        if direct_only and entry['stops'] > 0:
            continue
        code = entry['airline_iata']
        if entry['codeshare']:
            codeshares.append(code)
        else:
            if code not in operators:
                operators[code] = entry

    # Build result list — one row per operator
    results = []
    for code, entry in operators.items():
        airline_info = _AIRLINES_BY_IATA.get(code, {})
        results.append({
            'airline_iata': code,
            'airline_name': airline_info.get('name', code),
            'country': airline_info.get('country', ''),
            'active': airline_info.get('active', True),
            'equipment': entry['equipment'],
            'stops': entry['stops'],
            'codeshare_codes': [],  # filled below
        })

    # Attach codeshare codes to the result list (no reliable per-operator mapping
    # in routes.dat, so we list them once under all operators or as a shared block)
    codeshare_set = sorted(set(c for c in codeshares if c not in operators))
    for r in results:
        r['codeshare_codes'] = codeshare_set

    results.sort(key=lambda r: (not r['active'], r['airline_name']))
    return results
