import json

from django.test import TestCase, override_settings

from .models import Task


class MigrationTests(TestCase):
    def test_tasks_from_events_copied(self):
        self.assertEqual(Task.objects.count(), 5)
        self.assertFalse(Task.objects.exclude(executor=Task.Executor.COWORK).exists())
        self.assertEqual(Task.objects.first().name, 'Alle Künstler auslesen')


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
        self.assertEqual(tasks['count'], 7)
        self.assertNotIn('Alle Locations auslesen', [t['name'] for t in tasks['tasks']])

        task = self.call('get_task', {'name': 'morning briefing'})['structuredContent']
        self.assertEqual(task['parameters'], {'max': 5})
        self.assertEqual([(t['name'], t['executor']) for t in task['subtasks']],
                         [('E-Mails lesen', 'cowork'), ('Quotes holen', 'server')])
        self.assertTrue(self.call('get_task', {'name': 'Alle Locations auslesen'})['isError'])
