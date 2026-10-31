import datetime
import json
import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from tasks.models import Task

from .importer import import_events_json
from .models import Artist, Location, UpcomingEvent


class StartbestandTests(TestCase):
    def test_seed_data(self):
        self.assertEqual(Location.objects.count(), 6)
        self.assertFalse(Location.objects.exclude(rating=8).exists())
        self.assertEqual(Artist.objects.count(), 13)
        self.assertEqual(set(Artist.objects.filter(rating=6).values_list('name', flat=True)),
                         {'Hayley Williams', 'The Killers', 'Pink'})
        self.assertEqual(set(Artist.objects.filter(rating=7).values_list('name', flat=True)),
                         {'Harry Styles', 'James Blunt', 'Santiano'})
        cowork = Task.objects.filter(executor=Task.Executor.COWORK)
        self.assertEqual(cowork.count(), 5)
        for task in cowork:
            self.assertIn('LC Events', task.prompt, task.name)


class ImporterTests(TestCase):
    def test_import_creates_and_completes(self):
        Artist.objects.filter(name='Sting').update(info='')
        data = {
            'locations': [{'name': 'Piazza Napoleone, Lucca', 'country': 'Italien', 'rating': 9},
                          {'name': 'arena di verona', 'country': 'X', 'rating': 2, 'info': 'neu'}],
            'artists': [{'name': 'STING', 'rating': 3, 'info': 'ergänzt'}],
            'events': [{'location': 'Arena di Verona', 'artist': 'Sting', 'date': '2027-07-14',
                        'ticket_url': 'https://tickets.example.com/sting'},
                       {'location': 'Piazza Napoleone, Lucca', 'artist': 'Sting', 'date': '2027-07-16'}],
        }
        report = import_events_json(data)
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['created']['locations'], ['Piazza Napoleone, Lucca'])
        self.assertEqual(len(report['created']['events']), 2)

        verona = Location.objects.get(name='Arena di Verona')
        self.assertEqual((verona.rating, verona.country), (8, 'Italien'))  # bestehendes bleibt
        sting = Artist.objects.get(name='Sting')
        self.assertEqual((sting.rating, sting.info), (8, 'ergänzt'))  # nur leeres Feld ergänzt

        # zweiter Import: keine Duplikate, fehlende Event-Info wird ergänzt
        data['events'][1]['info'] = 'Lucca Summer Festival'
        report = import_events_json(data)
        self.assertEqual(report['updated']['events'], [str(UpcomingEvent.objects.get(location__name__startswith='Piazza'))])
        self.assertEqual(UpcomingEvent.objects.count(), 2)

    def test_errors_save_nothing(self):
        data = {
            'artists': [{'name': 'Neuer Artist'}],
            'events': [{'location': 'Gibt es nicht', 'artist': 'Sting', 'date': '2027-01-01'},
                       {'location': 'Lorelei', 'artist': 'Sting', 'date': '01.07.2027'}],
            'locations': [{'name': 'Ohne Land'}],
        }
        report = import_events_json(data)
        self.assertEqual(len(report['errors']), 3)
        self.assertFalse(Artist.objects.filter(name='Neuer Artist').exists())
        self.assertFalse(UpcomingEvent.objects.exists())

    def test_dry_run_and_bad_input(self):
        report = import_events_json({'artists': [{'name': 'Probe', 'rating': 5}]}, dry_run=True)
        self.assertEqual(report['created']['artists'], ['Probe'])
        self.assertFalse(Artist.objects.filter(name='Probe').exists())
        self.assertTrue(import_events_json([])['errors'])
        self.assertTrue(import_events_json({'artists': [{'name': 'X', 'rating': 11}]})['errors'])


class AdminImportTests(TestCase):
    def test_import_page(self):
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        url = '/admin/events/upcomingevent/import/'
        self.assertEqual(self.client.get(url).status_code, 200)
        payload = json.dumps({'events': [{'location': 'Lorelei', 'artist': 'Santiano', 'date': '2027-08-01'}]})
        r = self.client.post(url, {'json_text': payload, 'dry_run': 'on'})
        self.assertContains(r, 'Dry-Run')
        self.assertFalse(UpcomingEvent.objects.exists())
        r = self.client.post(url, {'json_text': payload})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(UpcomingEvent.objects.count(), 1)

    def test_import_page_requires_staff(self):
        self.assertEqual(self.client.get('/admin/events/upcomingevent/import/').status_code, 302)


@override_settings(MCP_READONLY_API_KEY='mcp-key', FINTECH_API_KEY='test-key')
class EventsMcpTests(TestCase):
    """Rein lesender MCP-Server unter /events/mcp (events.mcp_server)."""

    def rpc(self, method, params=None, token='mcp-key'):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
        return self.client.post('/events/mcp', data=json.dumps(body), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')

    def call(self, name, arguments=None):
        return self.rpc('tools/call', {'name': name, 'arguments': arguments or {}}).json()['result']

    def test_auth(self):
        self.assertEqual(self.rpc('ping', token='test-key').status_code, 401)
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        self.assertEqual(self.client.post('/events/mcp', data='{}', content_type='application/json').status_code, 401)
        self.assertEqual(self.client.get('/events/mcp', HTTP_AUTHORIZATION='Bearer mcp-key').status_code, 405)

    def test_tools_are_all_read_only(self):
        result = self.rpc('initialize', {'protocolVersion': '2025-06-18'}).json()['result']
        self.assertEqual(result['serverInfo']['name'], 'lc-app-events')
        tools = self.rpc('tools/list').json()['result']['tools']
        self.assertEqual({t['name'] for t in tools},
                         {'get_locations', 'get_artists', 'get_upcoming_events', 'get_import_format',
                          'get_tasks', 'get_task'})
        for tool in tools:
            self.assertTrue(tool['annotations']['readOnlyHint'], tool['name'])
            self.assertTrue(re.match(r'^get_', tool['name']), tool['name'])

    def test_tools(self):
        self.assertEqual(self.call('get_locations')['structuredContent']['count'], 6)
        artists = self.call('get_artists')['structuredContent']['artists']
        self.assertIn({'name': 'Hayley Williams', 'rating': 6}, [{k: a[k] for k in ('name', 'rating')} for a in artists])
        self.assertIn('example', self.call('get_import_format')['structuredContent'])

        today = datetime.date.today()
        lorelei, verona = Location.objects.get(name='Lorelei'), Location.objects.get(name='Arena di Verona')
        sting = Artist.objects.get(name='Sting')
        UpcomingEvent.objects.create(location=lorelei, artist=sting, date=today - datetime.timedelta(days=1))
        UpcomingEvent.objects.create(location=verona, artist=sting, date=today + datetime.timedelta(days=30))
        events = self.call('get_upcoming_events')['structuredContent']
        self.assertEqual([e['location'] for e in events['events']], ['Arena di Verona'])
        events = self.call('get_upcoming_events', {'from_date': '2000-01-01', 'location': 'lorelei'})['structuredContent']
        self.assertEqual(events['count'], 1)
        self.assertTrue(self.call('get_upcoming_events', {'from_date': 'morgen'})['isError'])

    def test_tasks(self):
        tasks = self.call('get_tasks')['structuredContent']['tasks']
        self.assertEqual(tasks[0]['name'], 'Alle Künstler auslesen')
        task = self.call('get_task', {'name': 'vorschläge für weitere upcoming events machen'})
        self.assertFalse(task['isError'])
        self.assertIn('get_import_format', task['structuredContent']['prompt'])
        task = self.call('get_task', {'name': 'Gibt es nicht'})
        self.assertTrue(task['isError'])
        self.assertEqual(len(task['structuredContent']['available']), 8)
