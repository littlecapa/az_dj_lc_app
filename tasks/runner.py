"""Protokolliert Läufe von Management-Commands als TaskRun (Grundlage für /tasks und den Health-Check).

Einbindung: class Command(TrackedCommandMixin, BaseCommand) mit task_command = '<command-name>'. Geloggt wird
nur, wenn es einen aktiven Task mit diesem command gibt. Fehler beim Loggen brechen den Command nie ab.
"""

import logging
import re
from contextlib import contextmanager
from datetime import timedelta

from django.utils import timezone

from .models import Task, TaskRun

logger = logging.getLogger(__name__)

# Ein Lauf, der so lange auf "running" steht, wurde von außen abgebrochen (z. B. GitHub-Actions-Timeout)
STALE_AFTER = timedelta(minutes=30)
_ANSI = re.compile(r'\x1b\[[0-9;]*m')


class _Tee:
    """Stream-Wrapper für self.stdout, merkt sich die letzte nicht-leere Zeile als Meldung für den TaskRun."""

    def __init__(self, out):
        self._out, self.last_line = out, ''

    def write(self, text):
        lines = [line.strip() for line in _ANSI.sub('', text).splitlines() if line.strip()]
        if lines:
            self.last_line = lines[-1]
        return self._out.write(text)

    def __getattr__(self, name):
        return getattr(self._out, name)


def mark_stale_runs(task):
    TaskRun.objects.filter(task=task, status=TaskRun.Status.RUNNING,
                           started_at__lt=timezone.now() - STALE_AFTER).update(
        status=TaskRun.Status.TIMEOUT, message='Kein Abschluss gemeldet (abgebrochen oder Timeout)')


def _safe(func, *args):
    try:
        return func(*args)
    except Exception:  # Logging darf den eigentlichen Job nie stören
        logger.exception('TaskRun-Protokollierung fehlgeschlagen')


@contextmanager
def track_run(command, message_source=None):
    """Legt für den aktiven Task mit diesem command einen TaskRun an und schließt ihn mit Erfolg/Fehler ab."""
    def start():
        task = Task.objects.filter(command=command, active=True).first()
        if task is None:
            return None
        mark_stale_runs(task)
        return TaskRun.objects.create(task=task)

    def finish(run, status, message):
        run.status, run.message, run.finished_at = status, message[:2000], timezone.now()
        run.save(update_fields=['status', 'message', 'finished_at'])

    run = _safe(start)
    try:
        yield run
    except BaseException as exc:
        if run:
            last = getattr(message_source, 'last_line', '')
            _safe(finish, run, TaskRun.Status.ERROR, f'{type(exc).__name__}: {exc}' + (f' | {last}' if last else ''))
        raise
    if run:
        _safe(finish, run, TaskRun.Status.SUCCESS, getattr(message_source, 'last_line', ''))


class TrackedCommandMixin:
    task_command = None
    # Ist eine dieser Optionen gesetzt, ist es ein Test- oder Teillauf → kein TaskRun
    untracked_options = ('dry_run',)

    def execute(self, *args, **options):
        if any(options.get(name) for name in self.untracked_options):
            return super().execute(*args, **options)
        tee = _Tee(options.get('stdout') or self.stdout._out)
        options['stdout'] = tee
        with track_run(self.task_command, tee):
            return super().execute(*args, **options)
