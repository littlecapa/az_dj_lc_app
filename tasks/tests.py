import datetime
import json
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from .health import FAILED, OK, OVERDUE, RUNNING, UNKNOWN, active_hours, task_health
from .models import Task, TaskRun
from .runner import TrackedCommandMixin


class MigrationTests(TestCase):
    def test_tasks_from_events_copied(self):
        self.assertEqual(Task.objects.filter(executor=Task.Executor.COWORK).count(), 5)
        self.assertEqual(Task.objects.first().name, 'Alle Künstler auslesen')

    def test_server_tasks_seeded(self):
        server = Task.objects.filter(executor=Task.Executor.SERVER)
        self.assertEqual(set(server.values_list('command', flat=True)),
                         {'update_prices', 'update_news', 'update_etf_holdings'})
        self.assertEqual(server.get(command='update_prices').run_days, '012345')


@override_settings(MCP_READONLY_API_KEY='mcp-key')
class TaskToolsTests(TestCase):
    """get_tasks / get_task, eingehängt in /events/mcp."""

    def call(self, name, arguments=None):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments or {}}}
        r = self.client.post('/events/mcp', data=json.dumps(body), content_type='application/json',
                             HTTP_AUTHORIZATION='Bearer mcp-key')
        return r.json()['result']

    def test_subtasks_and_inactive(self):
        main = Task.objects.create(name='Morning Briefing', prompt='Fasse zusammen', parameters={'max': 5})
        Task.objects.create(name='Quotes holen', parent=main, position=2, executor=Task.Executor.SERVER)
        Task.objects.create(name='E-Mails lesen', parent=main, position=1)
        Task.objects.create(name='Report alt', parent=main, position=3, active=False)
        Task.objects.filter(name='Alle Locations auslesen').update(active=False)

        tasks = self.call('get_tasks')['structuredContent']
        self.assertEqual(tasks['count'], 10)
        self.assertNotIn('Alle Locations auslesen', [t['name'] for t in tasks['tasks']])

        task = self.call('get_task', {'name': 'morning briefing'})['structuredContent']
        self.assertEqual(task['parameters'], {'max': 5})
        self.assertEqual([(t['name'], t['executor']) for t in task['subtasks']],
                         [('E-Mails lesen', 'cowork'), ('Quotes holen', 'server')])
        self.assertTrue(self.call('get_task', {'name': 'Alle Locations auslesen'})['isError'])


class DummyCommand(TrackedCommandMixin, BaseCommand):
    task_command = 'update_news'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--fail', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write('Starte …')
        if options['fail']:
            raise CommandError('Provider down')
        self.stdout.write(self.style.SUCCESS('Fertig: 3 neue Artikel.'))


class RunnerTests(TestCase):
    def run_cmd(self, *args):
        out = StringIO()
        call_command(DummyCommand(), *args, stdout=out)
        return out.getvalue()

    def test_success_error_and_dry_run(self):
        task = Task.objects.get(command='update_news')
        self.assertIn('Fertig: 3 neue Artikel.', self.run_cmd())
        run = task.runs.get()
        self.assertEqual((run.status, run.message), (TaskRun.Status.SUCCESS, 'Fertig: 3 neue Artikel.'))
        self.assertIsNotNone(run.finished_at)

        with self.assertRaises(CommandError):
            self.run_cmd('--fail')
        run = task.runs.first()
        self.assertEqual(run.status, TaskRun.Status.ERROR)
        self.assertEqual(run.message, 'CommandError: Provider down | Starte …')

        self.run_cmd('--dry-run')
        self.assertEqual(task.runs.count(), 2)

    def test_stale_run_becomes_timeout_and_inactive_task_not_logged(self):
        task = Task.objects.get(command='update_news')
        stale = TaskRun.objects.create(task=task, started_at=timezone.now() - datetime.timedelta(hours=2))
        self.run_cmd()
        stale.refresh_from_db()
        self.assertEqual(stale.status, TaskRun.Status.TIMEOUT)

        task.active = False
        task.save()
        self.run_cmd()
        self.assertEqual(task.runs.count(), 2)


def utc(*args):
    return datetime.datetime(*args, tzinfo=datetime.timezone.utc)


class HealthTests(TestCase):
    def setUp(self):
        self.task = Task.objects.get(command='update_prices')  # 24 h, Mo–Sa

    def run_at(self, started, status=TaskRun.Status.SUCCESS):
        return TaskRun.objects.create(task=self.task, started_at=started, finished_at=started, status=status)

    def test_active_hours_skip_sunday(self):
        # Sa 31.10.2026 12:00 UTC → Mo 02.11.2026 12:00 UTC: Sonntag zählt nicht
        self.assertAlmostEqual(active_hours(utc(2026, 10, 31, 12), utc(2026, 11, 2, 12), '012345'), 24)
        self.assertAlmostEqual(active_hours(utc(2026, 10, 31, 12), utc(2026, 11, 2, 12), '0123456'), 48)

    def test_status(self):
        self.assertEqual(task_health(self.task)[0], UNKNOWN)
        self.run_at(utc(2026, 10, 31, 9))  # Samstag
        self.assertEqual(task_health(self.task, now=utc(2026, 11, 2, 14))[0], OK)       # Montag, Sonntag zählt nicht
        self.assertEqual(task_health(self.task, now=utc(2026, 11, 3, 14))[0], OVERDUE)  # Dienstag
        TaskRun.objects.create(task=self.task, started_at=utc(2026, 11, 2, 8))
        self.assertEqual(task_health(self.task, now=utc(2026, 11, 2, 8, 10))[0], RUNNING)
        self.assertEqual(task_health(self.task, now=utc(2026, 11, 2, 9))[0], FAILED)  # hängt → Timeout
        self.run_at(utc(2026, 11, 2, 11), TaskRun.Status.ERROR)
        self.assertEqual(task_health(self.task, now=utc(2026, 11, 2, 12))[0], FAILED)


class TaskPageTests(TestCase):
    def test_staff_only(self):
        self.assertEqual(self.client.get('/tasks/').status_code, 302)
        self.client.force_login(User.objects.create_user('user', password='pw'))
        self.assertEqual(self.client.get('/tasks/').status_code, 302)

    def test_list_and_detail(self):
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        task = Task.objects.get(command='update_prices')
        TaskRun.objects.create(task=task, status=TaskRun.Status.ERROR, message='Yahoo 429')
        r = self.client.get('/tasks/')
        self.assertContains(r, 'Kurse aktualisieren')
        self.assertContains(r, 'Fehlgeschlagen')
        self.assertContains(r, 'Kein Log')  # Cowork-Tasks ohne Läufe
        r = self.client.get(f'/tasks/{task.pk}/')
        self.assertContains(r, 'Yahoo 429')
