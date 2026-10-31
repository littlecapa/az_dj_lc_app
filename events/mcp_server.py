"""
MCP-Server (Model Context Protocol) — rein lesender Zugriff auf Locations, Artists und
Upcoming Events für Claude, damit Claude nach neuen Konzerten suchen kann.

POST /events/mcp

Transport, JSON-RPC und Authentifizierung (Bearer MCP_READONLY_API_KEY): core.mcp_server.
Neue Konzerte schreibt Claude NICHT selbst, sondern liefert JSON im Format von
get_import_format, das manuell importiert wird (Admin → Upcoming Events → JSON importieren
oder `python manage.py import_events <datei.json>`).
"""

import datetime

from django.utils import timezone

from core.mcp_server import ReadOnlyMcpView
from tasks.mcp_tools import TASK_TOOLS

from .importer import IMPORT_FORMAT
from .models import Artist, Location, UpcomingEvent

SERVER_INFO = {"name": "lc-app-events", "title": "LC Events (read-only)", "version": "1.0.0"}
INSTRUCTIONS = (
    "Read-only access to the owner's favourite concert locations, artists and already known "
    "upcoming events. Ratings are 1-10 (10 = very good). Typical workflow: read locations, artists "
    "and upcoming events, search the web for new concerts of these artists and/or at these "
    "locations, and return the findings as JSON in the format of get_import_format — only events "
    "that are not already listed. New artists or locations may be suggested in the same JSON. "
    "This server cannot write; the owner imports the JSON manually. Predefined tasks with their "
    "prompts are available via get_tasks / get_task — when asked to run a task, fetch its prompt "
    "with get_task and follow it."
)

_DATE = {"type": "string", "format": "date", "description": "ISO date YYYY-MM-DD"}


def _location(loc):
    return {"name": loc.name, "country": loc.country, "info": loc.info,
            "picture_url": loc.picture_url or None, "rating": loc.rating}


def _artist(artist):
    return {"name": artist.name, "rating": artist.rating, "info": artist.info,
            "song_url": artist.song_url or None}


def _event(event):
    return {"location": event.location.name, "country": event.location.country,
            "artist": event.artist.name, "date": event.date.isoformat(), "info": event.info,
            "ticket_url": event.ticket_url or None}


def _parse_date(value, field):
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"'{field}' must be YYYY-MM-DD")


def _locations(args):
    locations = [_location(loc) for loc in Location.objects.all()]
    return 200, {"count": len(locations), "locations": locations}


def _artists(args):
    artists = [_artist(a) for a in Artist.objects.all()]
    return 200, {"count": len(artists), "artists": artists}


def _upcoming_events(args):
    try:
        from_date = _parse_date(args["from_date"], "from_date") if args.get("from_date") else timezone.localdate()
        to_date = _parse_date(args["to_date"], "to_date") if args.get("to_date") else None
    except ValueError as exc:
        return 400, {"error": str(exc)}
    events = UpcomingEvent.objects.select_related("location", "artist").filter(date__gte=from_date)
    if to_date:
        events = events.filter(date__lte=to_date)
    if args.get("artist"):
        events = events.filter(artist__name__iexact=args["artist"].strip())
    if args.get("location"):
        events = events.filter(location__name__iexact=args["location"].strip())
    result = [_event(e) for e in events]
    return 200, {"from_date": from_date.isoformat(), "count": len(result), "events": result}


TOOLS = {
    "get_locations": {
        "title": "Locations",
        "description": "All favourite concert locations with country, info, picture link and rating (1-10).",
        "inputSchema": {"type": "object", "properties": {}},
        "run": _locations,
    },
    "get_artists": {
        "title": "Artists",
        "description": "All favourite artists with rating (1-10), info and a song link.",
        "inputSchema": {"type": "object", "properties": {}},
        "run": _artists,
    },
    "get_upcoming_events": {
        "title": "Upcoming events",
        "description": "Already known upcoming concerts (location, artist, date, info, ticket link), "
                       "sorted by date. By default from today on.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_date": {**_DATE, "description": "Earliest date (YYYY-MM-DD), default today"},
                "to_date": {**_DATE, "description": "Latest date (YYYY-MM-DD), optional"},
                "artist": {"type": "string", "description": "Artist name (case-insensitive), optional"},
                "location": {"type": "string", "description": "Location name (case-insensitive), optional"},
            },
        },
        "run": _upcoming_events,
    },
    "get_import_format": {
        "title": "Import format",
        "description": "JSON format (with example) in which newly found concerts, artists and locations "
                       "must be returned so the owner can import them.",
        "inputSchema": {"type": "object", "properties": {}},
        "run": lambda a: (200, IMPORT_FORMAT),
    },
    **TASK_TOOLS,
}


class EventsMcpView(ReadOnlyMcpView):
    TOOLS = TOOLS
    SERVER_INFO = SERVER_INFO
    INSTRUCTIONS = INSTRUCTIONS
