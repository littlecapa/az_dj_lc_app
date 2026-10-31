"""
MCP-Server (Model Context Protocol) — rein lesender Zugriff auf Venues, Artists und
Upcoming Events für Claude, damit Claude nach neuen Konzerten suchen kann.

POST /leisure/mcp (übergangsweise auch noch POST /events/mcp)

Transport, JSON-RPC und Authentifizierung (Bearer MCP_READONLY_API_KEY): core.mcp_server.
Neue Konzerte schreibt Claude NICHT selbst, sondern liefert JSON im Format von
get_import_format, das manuell importiert wird (Admin → Leisure → Upcoming Events → JSON importieren
oder `python manage.py import_events <datei.json>`).
"""

import datetime

from django.utils import timezone

from core.mcp_server import ReadOnlyMcpView, WriteMcpView
from tasks.mcp_tools import TASK_TOOLS, TASK_WRITE_TOOLS

from .importer import IMPORT_FORMAT
from .models import Artist, Category, Suggestion, UpcomingEvent, Venue
from .suggestions import MAX_PER_CALL, add_artist_suggestions

SERVER_INFO = {"name": "lc-app-leisure", "title": "LC Leisure (read-only)", "version": "2.0.0"}
INSTRUCTIONS = (
    "Read-only access to the owner's favourite concert venues, artists and already known "
    "upcoming events. Ratings are 1-10 (10 = very good). Typical workflow: read venues, artists "
    "and upcoming events, search the web for new concerts of these artists and/or at these "
    "venues, and return the findings as JSON in the format of get_import_format — only events "
    "that are not already listed. New artists or venues may be suggested in the same JSON. "
    "This server cannot write; the owner imports the JSON manually. Predefined tasks with their "
    "prompts are available via get_tasks / get_task — when asked to run a task, fetch its prompt "
    "with get_task and follow it."
)

_DATE = {"type": "string", "format": "date", "description": "ISO date YYYY-MM-DD"}


def _venue(venue):
    return {"name": venue.name, "country": venue.country, "info": venue.info,
            "picture_url": venue.picture_url or None, "rating": venue.rating}


def _artist(artist):
    return {"name": artist.name, "category": artist.category.name if artist.category else None,
            "rating": artist.rating, "info": artist.info,
            "song_url": artist.song_url or None}


def _event(event):
    return {"venue": event.venue.name, "country": event.venue.country,
            "artist": event.artist.name, "date": event.date.isoformat(), "info": event.info,
            "ticket_url": event.ticket_url or None}


def _parse_date(value, field):
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"'{field}' must be YYYY-MM-DD")


def _venues(args):
    venues = [_venue(v) for v in Venue.objects.all()]
    return 200, {"count": len(venues), "venues": venues}


def _artists(args):
    artists = [_artist(a) for a in Artist.objects.select_related("category")]
    return 200, {"count": len(artists), "artists": artists}


def _upcoming_events(args):
    try:
        from_date = _parse_date(args["from_date"], "from_date") if args.get("from_date") else timezone.localdate()
        to_date = _parse_date(args["to_date"], "to_date") if args.get("to_date") else None
    except ValueError as exc:
        return 400, {"error": str(exc)}
    events = UpcomingEvent.objects.select_related("venue", "artist").filter(date__gte=from_date)
    if to_date:
        events = events.filter(date__lte=to_date)
    if args.get("artist"):
        events = events.filter(artist__name__iexact=args["artist"].strip())
    if args.get("venue"):
        events = events.filter(venue__name__iexact=args["venue"].strip())
    result = [_event(e) for e in events]
    return 200, {"from_date": from_date.isoformat(), "count": len(result), "events": result}


def _categories(args):
    return 200, {"categories": list(Category.objects.values_list("name", flat=True))}


def _suggestions(args):
    suggestions = Suggestion.objects.select_related("category")
    for field in ("kind", "status"):
        if args.get(field):
            suggestions = suggestions.filter(**{field: args[field]})
    result = [{"kind": s.kind, "name": s.name, "category": s.category.name if s.category else None,
               "status": s.status, "rating": s.rating, "info": s.info, "created_at": s.created_at.date().isoformat()}
              for s in suggestions]
    return 200, {"count": len(result), "suggestions": result}


def _add_suggestions(args):
    if args.get("kind", "artist") != "artist":
        return 400, {"error": "Bisher werden nur Artist-Vorschläge unterstützt (kind = artist)."}
    if not isinstance(args.get("suggestions"), list):
        return 400, {"error": "'suggestions' muss eine Liste sein"}
    return 200, add_artist_suggestions(args["suggestions"])


TOOLS = {
    "get_venues": {
        "title": "Venues",
        "description": "All favourite concert venues with country, info, picture link and rating (1-10).",
        "inputSchema": {"type": "object", "properties": {}},
        "run": _venues,
    },
    "get_artists": {
        "title": "Artists",
        "description": "All favourite artists with rating (1-10), info and a song link.",
        "inputSchema": {"type": "object", "properties": {}},
        "run": _artists,
    },
    "get_upcoming_events": {
        "title": "Upcoming events",
        "description": "Already known upcoming concerts (venue, artist, date, info, ticket link), "
                       "sorted by date. By default from today on.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_date": {**_DATE, "description": "Earliest date (YYYY-MM-DD), default today"},
                "to_date": {**_DATE, "description": "Latest date (YYYY-MM-DD), optional"},
                "artist": {"type": "string", "description": "Artist name (case-insensitive), optional"},
                "venue": {"type": "string", "description": "Venue name (case-insensitive), optional"},
            },
        },
        "run": _upcoming_events,
    },
    "get_import_format": {
        "title": "Import format",
        "description": "JSON format (with example) in which newly found concerts, artists and venues "
                       "must be returned so the owner can import them.",
        "inputSchema": {"type": "object", "properties": {}},
        "run": lambda a: (200, IMPORT_FORMAT),
    },
    "get_categories": {
        "title": "Categories",
        "description": "Allowed categories (e.g. genre of an artist). Suggestions must use one of these names.",
        "inputSchema": {"type": "object", "properties": {}},
        "run": _categories,
    },
    "get_suggestions": {
        "title": "Suggestions",
        "description": "Earlier suggestions of new artists/venues/events with their status: pending (not yet rated "
                       "by the owner), accepted (now in the lists) or rejected (blacklist — never suggest again). "
                       "Newest first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["artist", "venue", "event"], "description": "optional"},
                "status": {"type": "string", "enum": ["pending", "accepted", "rejected"], "description": "optional"},
            },
        },
        "run": _suggestions,
    },
    **TASK_TOOLS,
}


class LeisureMcpView(ReadOnlyMcpView):
    TOOLS = TOOLS
    SERVER_INFO = SERVER_INFO
    INSTRUCTIONS = INSTRUCTIONS


WRITE_SERVER_INFO = {"name": "lc-app-leisure-write", "title": "LC Leisure (suggestions)", "version": "1.0.0"}
WRITE_INSTRUCTIONS = (
    "Narrow write access for the owner's leisure lists: store suggestions of new artists for the owner to rate "
    "(they never go into the lists directly) and report task runs. Read the current data with the read-only "
    "server lc-app-leisure first (get_artists, get_categories, get_suggestions)."
)

WRITE_TOOLS = {
    "add_suggestions": {
        "title": "Add suggestions",
        "description": f"Store up to {MAX_PER_CALL} suggested new artists for the owner to rate. Names that already "
                       "exist as artist or as pending/accepted/rejected suggestion are skipped (reason returned). "
                       "category must be one of get_categories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["artist"], "description": "Currently only 'artist'"},
                "suggestions": {
                    "type": "array",
                    "maxItems": MAX_PER_CALL,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "category": {"type": "string", "description": "One of get_categories"},
                            "info": {"type": "string", "description": "German, 1-2 sentences: why it fits, tour info"},
                            "song_url": {"type": "string", "description": "Verified official YouTube/Spotify link, optional"},
                        },
                        "required": ["name", "category", "info"],
                    },
                },
            },
            "required": ["suggestions"],
        },
        "run": _add_suggestions,
    },
    **TASK_WRITE_TOOLS,
}


class LeisureWriteMcpView(WriteMcpView):
    TOOLS = WRITE_TOOLS
    SERVER_INFO = WRITE_SERVER_INFO
    INSTRUCTIONS = WRITE_INSTRUCTIONS
