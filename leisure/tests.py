import datetime
import json
import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from tasks.models import Task

from .importer import import_events_json
from .models import Artist, Category, Suggestion, UpcomingEvent, Venue


class StartbestandTests(TestCase):
    def test_seed_data(self):
        self.assertEqual(Venue.objects.count(), 6)
        self.assertFalse(Venue.objects.exclude(rating=8).exists())
        self.assertEqual(Artist.objects.count(), 13)
        self.assertEqual(set(Artist.objects.filter(rating=6).values_list('name', flat=True)),
                         {'Hayley Williams', 'The Killers', 'Pink'})
        self.assertEqual(set(Artist.objects.filter(rating=7).values_list('name', flat=True)),
                         {'Harry Styles', 'James Blunt', 'Santiano'})
        self.assertEqual(Category.objects.count(), 6)
        self.assertFalse(Artist.objects.filter(category__isnull=True).exists())
        self.assertEqual(Artist.objects.get(name='John Cleese').category.name, 'Comedy')
        claude_tasks = Task.objects.exclude(executor=Task.Executor.SERVER)
        self.assertEqual(claude_tasks.count(), 5)
        for task in claude_tasks:
            self.assertIn('LC Leisure', task.prompt, task.name)
            self.assertNotIn('ocation', task.prompt, task.name)


class ImporterTests(TestCase):
    def test_import_creates_and_completes(self):
        Artist.objects.filter(name='Sting').update(info='')
        data = {
            'venues': [{'name': 'Piazza Napoleone, Lucca', 'country': 'Italien', 'rating': 9},
                          {'name': 'arena di verona', 'country': 'X', 'rating': 2, 'info': 'neu'}],
            'artists': [{'name': 'STING', 'rating': 3, 'info': 'ergänzt'}],
            'events': [{'venue': 'Arena di Verona', 'artist': 'Sting', 'date': '2027-07-14',
                        'ticket_url': 'https://tickets.example.com/sting'},
                       {'venue': 'Piazza Napoleone, Lucca', 'artist': 'Sting', 'date': '2027-07-16'}],
        }
        report = import_events_json(data)
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['created']['venues'], ['Piazza Napoleone, Lucca'])
        self.assertEqual(len(report['created']['events']), 2)

        verona = Venue.objects.get(name='Arena di Verona')
        self.assertEqual((verona.rating, verona.country), (8, 'Italien'))  # bestehendes bleibt
        sting = Artist.objects.get(name='Sting')
        self.assertEqual((sting.rating, sting.info), (8, 'ergänzt'))  # nur leeres Feld ergänzt

        # zweiter Import: keine Duplikate, fehlende Event-Info wird ergänzt
        data['events'][1]['info'] = 'Lucca Summer Festival'
        report = import_events_json(data)
        self.assertEqual(report['updated']['events'], [str(UpcomingEvent.objects.get(venue__name__startswith='Piazza'))])
        self.assertEqual(UpcomingEvent.objects.count(), 2)

    def test_errors_save_nothing(self):
        data = {
            'artists': [{'name': 'Neuer Artist'}],
            'events': [{'venue': 'Gibt es nicht', 'artist': 'Sting', 'date': '2027-01-01'},
                       {'venue': 'Lorelei', 'artist': 'Sting', 'date': '01.07.2027'}],
            'venues': [{'name': 'Ohne Land'}],
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

    def test_old_location_keys_still_accepted(self):
        data = {'locations': [{'name': 'Neue Bühne', 'country': 'Schweiz'}],
                'events': [{'location': 'Neue Bühne', 'artist': 'Sting', 'date': '2027-05-01'}]}
        report = import_events_json(data)
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['created']['venues'], ['Neue Bühne'])
        self.assertTrue(UpcomingEvent.objects.filter(venue__name='Neue Bühne').exists())


class AdminImportTests(TestCase):
    def test_import_page(self):
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        url = '/admin/leisure/upcomingevent/import/'
        self.assertEqual(self.client.get(url).status_code, 200)
        payload = json.dumps({'events': [{'venue': 'Lorelei', 'artist': 'Santiano', 'date': '2027-08-01'}]})
        r = self.client.post(url, {'json_text': payload, 'dry_run': 'on'})
        self.assertContains(r, 'Dry-Run')
        self.assertFalse(UpcomingEvent.objects.exists())
        r = self.client.post(url, {'json_text': payload})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(UpcomingEvent.objects.count(), 1)

    def test_import_page_requires_staff(self):
        self.assertEqual(self.client.get('/admin/leisure/upcomingevent/import/').status_code, 302)


@override_settings(MCP_READONLY_API_KEY='mcp-key', FINTECH_API_KEY='test-key')
class LeisureMcpTests(TestCase):
    """Rein lesender MCP-Server unter /leisure/mcp (leisure.mcp_server), übergangsweise auch /events/mcp."""

    def rpc(self, method, params=None, token='mcp-key', url='/leisure/mcp'):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
        return self.client.post(url, data=json.dumps(body), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')

    def call(self, name, arguments=None):
        return self.rpc('tools/call', {'name': name, 'arguments': arguments or {}}).json()['result']

    def test_auth(self):
        self.assertEqual(self.rpc('ping', token='test-key').status_code, 401)
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        self.assertEqual(self.client.post('/leisure/mcp', data='{}', content_type='application/json').status_code, 401)
        self.assertEqual(self.client.get('/leisure/mcp', HTTP_AUTHORIZATION='Bearer mcp-key').status_code, 405)

    def test_old_url_still_works(self):
        result = self.rpc('initialize', {'protocolVersion': '2025-06-18'}, url='/events/mcp').json()['result']
        self.assertEqual(result['serverInfo']['name'], 'lc-app-leisure')

    def test_tools_are_all_read_only(self):
        result = self.rpc('initialize', {'protocolVersion': '2025-06-18'}).json()['result']
        self.assertEqual(result['serverInfo']['name'], 'lc-app-leisure')
        tools = self.rpc('tools/list').json()['result']['tools']
        self.assertEqual({t['name'] for t in tools},
                         {'get_venues', 'get_artists', 'get_upcoming_events', 'get_import_format',
                          'get_categories', 'get_suggestions', 'get_tasks', 'get_task'})
        for tool in tools:
            self.assertTrue(tool['annotations']['readOnlyHint'], tool['name'])
            self.assertTrue(re.match(r'^get_', tool['name']), tool['name'])

    def test_tools(self):
        self.assertEqual(self.call('get_venues')['structuredContent']['count'], 6)
        artists = self.call('get_artists')['structuredContent']['artists']
        self.assertIn({'name': 'Hayley Williams', 'rating': 6}, [{k: a[k] for k in ('name', 'rating')} for a in artists])
        self.assertIn('example', self.call('get_import_format')['structuredContent'])

        today = datetime.date.today()
        lorelei, verona = Venue.objects.get(name='Lorelei'), Venue.objects.get(name='Arena di Verona')
        sting = Artist.objects.get(name='Sting')
        UpcomingEvent.objects.create(venue=lorelei, artist=sting, date=today - datetime.timedelta(days=1))
        UpcomingEvent.objects.create(venue=verona, artist=sting, date=today + datetime.timedelta(days=30))
        events = self.call('get_upcoming_events')['structuredContent']
        self.assertEqual([e['venue'] for e in events['events']], ['Arena di Verona'])
        events = self.call('get_upcoming_events', {'from_date': '2000-01-01', 'venue': 'lorelei'})['structuredContent']
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


@override_settings(MCP_READONLY_API_KEY='mcp-key', MCP_WRITE_API_KEY='write-key')
class SuggestionTests(TestCase):
    """Schreib-MCP /leisure/mcp/write (add_suggestions, log_task_run) und Formular /leisure/new_artists."""

    def rpc(self, method, params=None, token='write-key', url='/leisure/mcp/write'):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
        return self.client.post(url, data=json.dumps(body), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')

    def call(self, name, arguments, **kwargs):
        return self.rpc('tools/call', {'name': name, 'arguments': arguments}, **kwargs).json()['result']

    def add(self, *items):
        return self.call('add_suggestions', {'kind': 'artist', 'suggestions': list(items)})['structuredContent']

    def test_write_endpoint_auth_and_tools(self):
        self.assertEqual(self.rpc('ping', token='mcp-key').status_code, 401)  # Lese-Key darf nicht schreiben
        self.assertEqual(self.rpc('ping').status_code, 200)
        self.assertEqual(self.rpc('ping', url='/leisure/mcp').status_code, 401)  # Schreib-Key nicht auf Lese-Server
        tools = self.rpc('tools/list').json()['result']['tools']
        self.assertEqual({t['name'] for t in tools}, {'add_suggestions', 'log_task_run'})
        self.assertFalse(any(t['annotations']['readOnlyHint'] for t in tools))

    def test_add_suggestions(self):
        result = self.add(
            {'name': 'Tom Odell', 'category': 'singer-songwriter', 'info': 'Wie Ed Sheeran.',
             'song_url': 'https://www.youtube.com/watch?v=abc'},
            {'name': 'sting', 'category': 'Pop', 'info': 'x'},
            {'name': 'Neu', 'category': 'Techno', 'info': 'x'},
            {'name': 'Kaputt', 'category': 'Pop', 'info': 'x', 'song_url': 'kein link'},
        )
        self.assertEqual(result['created'], ['Tom Odell'])
        reasons = {s['name']: s['reason'] for s in result['skipped']}
        self.assertIn('schon als Artist', reasons['sting'])
        self.assertIn('unbekannte Kategorie', reasons['Neu'])
        self.assertIn('keine gültige URL', reasons['Kaputt'])
        suggestion = Suggestion.objects.get(name='Tom Odell')
        self.assertEqual((suggestion.category.name, suggestion.payload), ('Singer-Songwriter', {'song_url': 'https://www.youtube.com/watch?v=abc'}))

        self.assertIn('noch offen', self.add({'name': 'TOM ODELL', 'category': 'Pop', 'info': 'x'})['skipped'][0]['reason'])
        many = [{'name': f'Band {i}', 'category': 'Rock', 'info': 'x'} for i in range(7)]
        self.assertEqual(len(self.add(*many)['created']), 5)
        self.assertTrue(self.call('add_suggestions', {'kind': 'venue', 'suggestions': [{'name': 'X'}]})['isError'])

        read = self.call('get_suggestions', {'status': 'pending'}, token='mcp-key', url='/leisure/mcp')['structuredContent']
        self.assertEqual(read['count'], 6)

    def test_log_task_run(self):
        from tasks.health import OK, task_health
        result = self.call('log_task_run', {'task': 'vorschläge für neue künstler machen', 'status': 'success',
                                            'message': '2 neue Vorschläge'})
        self.assertFalse(result['isError'])
        task = Task.objects.get(name='Vorschläge für neue Künstler machen')
        self.assertEqual(task.executor, Task.Executor.CLOUD)
        self.assertEqual(task_health(task)[0], OK)
        self.assertEqual(task.runs.get().message, '2 neue Vorschläge')
        self.assertTrue(self.call('log_task_run', {'task': 'Kurse aktualisieren', 'status': 'success'})['isError'])
        self.assertTrue(self.call('log_task_run', {'task': 'Alle Venues auslesen', 'status': 'kaputt'})['isError'])

    def test_review_form(self):
        self.assertEqual(self.client.get('/leisure/new_artists').status_code, 302)
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        self.add({'name': 'Tom Odell', 'category': 'Singer-Songwriter', 'info': 'Wie Ed Sheeran.',
                  'song_url': 'https://www.youtube.com/watch?v=abc'},
                 {'name': 'Nickelback', 'category': 'Rock', 'info': 'x'},
                 {'name': 'Später', 'category': 'Pop', 'info': 'x'})
        tom, nickel, later = (Suggestion.objects.get(name=n) for n in ('Tom Odell', 'Nickelback', 'Später'))
        r = self.client.get('/leisure/new_artists')
        self.assertContains(r, 'Tom Odell')
        self.assertContains(r, 'Singer-Songwriter')

        r = self.client.post('/leisure/new_artists', {f'verdict_{tom.pk}': 'up'}, follow=True)
        self.assertContains(r, 'braucht ein Rating')
        tom.refresh_from_db()
        self.assertEqual(tom.status, Suggestion.Status.PENDING)

        self.client.post('/leisure/new_artists', {f'verdict_{tom.pk}': 'up', f'rating_{tom.pk}': '7',
                                                  f'verdict_{nickel.pk}': 'down', f'rating_{later.pk}': '9'})
        artist = Artist.objects.get(name='Tom Odell')
        self.assertEqual((artist.rating, artist.category.name, artist.song_url),
                         (7, 'Singer-Songwriter', 'https://www.youtube.com/watch?v=abc'))
        self.assertEqual(Suggestion.objects.get(pk=nickel.pk).status, Suggestion.Status.REJECTED)
        self.assertEqual(Suggestion.objects.get(pk=later.pk).status, Suggestion.Status.PENDING)
        self.assertIn('Blacklist', self.add({'name': 'Nickelback', 'category': 'Rock', 'info': 'x'})['skipped'][0]['reason'])
