"""Health-Status je Task: rot, wenn der letzte Lauf fehlgeschlagen ist oder der letzte erfolgreiche Lauf
überfällig ist (Intervall + 25 % Toleranz, gezählt werden nur Stunden an den Lauftagen)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import TaskRun
from .runner import STALE_AFTER

LOCAL_TZ = ZoneInfo('Europe/Berlin')
TOLERANCE = 1.25

OK, RUNNING, FAILED, OVERDUE, UNKNOWN = 'ok', 'running', 'failed', 'overdue', 'unknown'
LABELS = {OK: 'OK', RUNNING: 'Läuft', FAILED: 'Fehlgeschlagen', OVERDUE: 'Überfällig', UNKNOWN: 'Kein Log'}


def active_hours(start, end, run_days):
    """Stunden zwischen start und end, die auf einen der Lauftage fallen (Ortszeit Berlin)."""
    start, end = start.astimezone(LOCAL_TZ), end.astimezone(LOCAL_TZ)
    total, day = 0.0, start.date()
    while day <= end.date():
        if str(day.weekday()) in run_days:
            day_start = datetime.combine(day, time.min, LOCAL_TZ)
            overlap = min(end, day_start + timedelta(days=1)) - max(start, day_start)
            total += max(overlap.total_seconds(), 0) / 3600
        day += timedelta(days=1)
    return total


def task_health(task, now=None):
    """(status, letzter Lauf, letzter erfolgreicher Lauf)"""
    now = now or timezone.now()
    runs = TaskRun.objects.filter(task=task)
    last = runs.first()
    last_success = runs.filter(status=TaskRun.Status.SUCCESS).first()
    if last is None:
        return UNKNOWN, None, None
    if last.status == TaskRun.Status.RUNNING and now - last.started_at < STALE_AFTER:
        status = RUNNING
    elif last.status != TaskRun.Status.SUCCESS:
        status = FAILED  # error, timeout oder hängender running-Lauf
    else:
        status = OK
    if status != FAILED and task.interval_hours:
        since = last_success.started_at if last_success else last.started_at
        if active_hours(since, now, task.run_days) > task.interval_hours * TOLERANCE:
            status = OVERDUE
    return status, last, last_success
