import datetime
import json
import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from tasks.models import Task

from .importer import import_events_json
from .models import Artist, Category, EventVote, Suggestion, UpcomingEvent, Venue


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
        self.assertIn('kind = event', task['structuredContent']['prompt'])
        task = self.call('get_task', {'name': 'Gibt es nicht'})
        self.assertTrue(task['isError'])
        self.assertEqual(len(task['structuredContent']['available']), 8)


@override_settings(MCP_READONLY_API_KEY='mcp-key', MCP_WRITE_API_KEY='write-key')
class SuggestionTests(TestCase):
    """Schreib-MCP /leisure/mcp/write (add_suggestions, log_task_run) und Formulare /leisure/new_artists, new_venues,
    new_events."""

    def rpc(self, method, params=None, token='write-key', url='/leisure/mcp/write'):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
        return self.client.post(url, data=json.dumps(body), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')

    def call(self, name, arguments, **kwargs):
        return self.rpc('tools/call', {'name': name, 'arguments': arguments}, **kwargs).json()['result']

    def add(self, *items, kind='artist'):
        return self.call('add_suggestions', {'kind': kind, 'suggestions': list(items)})['structuredContent']

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
        self.assertTrue(self.call('add_suggestions', {'kind': 'konzert', 'suggestions': [{'name': 'X'}]})['isError'])

        read = self.call('get_suggestions', {'status': 'pending'}, token='mcp-key', url='/leisure/mcp')['structuredContent']
        self.assertEqual(read['count'], 6)

    def test_add_venue_suggestions(self):
        existing = Venue.objects.first()
        result = self.add(
            {'name': 'Seebühne Bregenz', 'country': 'Österreich', 'info': 'Bühne im See.',
             'picture_url': 'https://upload.wikimedia.org/bregenz.jpg'},
            {'name': existing.name.upper(), 'country': 'Italien', 'info': 'x'},
            {'name': 'Ohne Land', 'info': 'x'},
            {'name': 'Tom Odell', 'country': 'England', 'info': 'x'},  # Name als Artist-Vorschlag stört nicht
            kind='venue')
        self.assertEqual(result['created'], ['Seebühne Bregenz', 'Tom Odell'])
        reasons = {s['name']: s['reason'] for s in result['skipped']}
        self.assertIn('schon als Venue', reasons[existing.name.upper()])
        self.assertIn('country', reasons['Ohne Land'])
        arena = Suggestion.objects.get(name='Seebühne Bregenz')
        self.assertEqual((arena.kind, arena.category, arena.payload),
                         ('venue', None, {'country': 'Österreich', 'picture_url': 'https://upload.wikimedia.org/bregenz.jpg'}))
        read = self.call('get_suggestions', {'kind': 'venue'}, token='mcp-key', url='/leisure/mcp')['structuredContent']
        self.assertEqual({s['country'] for s in read['suggestions']}, {'Österreich', 'England'})

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

    def test_venue_review_form(self):
        self.assertEqual(self.client.get('/leisure/new_venues').status_code, 302)
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        self.add({'name': 'Seebühne Bregenz', 'country': 'Österreich', 'info': 'Bühne im See.',
                  'picture_url': 'https://upload.wikimedia.org/bregenz.jpg'},
                 {'name': 'Mehrzweckhalle', 'country': 'Deutschland', 'info': 'x'}, kind='venue')
        self.add({'name': 'Tom Odell', 'category': 'Pop', 'info': 'x'})
        arena, halle = (Suggestion.objects.get(kind='venue', name=n) for n in ('Seebühne Bregenz', 'Mehrzweckhalle'))
        r = self.client.get('/leisure/new_venues')
        self.assertContains(r, 'Neue Venues')
        self.assertContains(r, 'Österreich')
        self.assertContains(r, '🖼 Bild')
        self.assertNotContains(r, 'Tom Odell')

        self.client.post('/leisure/new_venues', {f'verdict_{arena.pk}': 'up', f'rating_{arena.pk}': '9',
                                                 f'verdict_{halle.pk}': 'down'})
        venue = Venue.objects.get(name='Seebühne Bregenz')
        self.assertEqual((venue.rating, venue.country, venue.picture_url),
                         (9, 'Österreich', 'https://upload.wikimedia.org/bregenz.jpg'))
        self.assertEqual(Suggestion.objects.get(pk=halle.pk).status, Suggestion.Status.REJECTED)
        self.assertIn('Blacklist', self.add({'name': 'mehrzweckhalle', 'country': 'Deutschland', 'info': 'x'},
                                            kind='venue')['skipped'][0]['reason'])
        task = Task.objects.get(name='Vorschläge für neue Venues machen')
        self.assertEqual((task.executor, task.interval_hours), (Task.Executor.CLOUD, 744))
        self.assertIn('/leisure/new_venues', task.prompt)

    def test_add_event_suggestions(self):
        future = (datetime.date.today() + datetime.timedelta(days=200)).isoformat()
        UpcomingEvent.objects.create(artist=Artist.objects.get(name='Sting'),
                                     venue=Venue.objects.get(name='Arena di Verona'),
                                     date=datetime.date.fromisoformat(future))
        Suggestion.objects.create(kind='venue', name='Mehrzweckhalle', status='rejected', payload={'country': 'Deutschland'})
        result = self.add(
            {'artist': 'sting', 'venue': 'arena di verona', 'date': future, 'info': 'schon bekannt'},
            {'artist': 'Sting', 'venue': 'Lorelei', 'date': future, 'info': 'Tour 2027',
             'ticket_url': 'https://www.eventim.de/sting'},
            {'artist': 'Sting', 'venue': 'Seebühne Bregenz', 'date': future, 'info': 'x', 'country': 'Österreich',
             'venue_info': 'Bühne im Bodensee'},
            {'artist': 'Sting', 'venue': 'Ohne Land', 'date': future, 'info': 'x'},
            {'artist': 'Pink', 'venue': 'Irgendwo', 'date': future, 'info': 'x', 'country': 'Italien'},
            {'artist': 'Sting', 'venue': 'Mehrzweckhalle', 'date': future, 'info': 'x', 'country': 'Deutschland'},
            {'artist': 'Unbekannt', 'venue': 'Lorelei', 'date': future, 'info': 'x'},
            {'artist': 'Sting', 'venue': 'Lorelei', 'date': '2020-01-01', 'info': 'x'},
            {'artist': 'Sting', 'venue': 'Lorelei', 'date': '14.07.2027', 'info': 'x'},
            kind='event')
        self.assertEqual(result['created'], [f'Sting @ Lorelei, {future}', f'Sting @ Seebühne Bregenz, {future}'])
        reasons = [s['reason'] for s in result['skipped']]
        for expected in ('schon als Upcoming Event', '"country" fehlt', 'Rating ab 7', 'Blacklist',
                         'unbekannter Artist', 'Vergangenheit', 'YYYY-MM-DD'):
            self.assertTrue(any(expected in r for r in reasons), expected)
        lorelei = Suggestion.objects.get(kind='event', name=f'Sting @ Lorelei, {future}')
        self.assertEqual(lorelei.payload, {'artist': 'Sting', 'venue': 'Lorelei', 'date': future,
                                           'ticket_url': 'https://www.eventim.de/sting'})
        venue_suggestion = Suggestion.objects.get(kind='venue', name='Seebühne Bregenz')
        self.assertEqual((venue_suggestion.info, venue_suggestion.payload), ('Bühne im Bodensee', {'country': 'Österreich'}))
        again = self.add({'artist': 'STING', 'venue': 'lorelei', 'date': future, 'info': 'x'}, kind='event')
        self.assertIn('noch offen', again['skipped'][0]['reason'])

    def test_event_review_form(self):
        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        future = datetime.date.today() + datetime.timedelta(days=100)
        self.add({'artist': 'Sting', 'venue': 'Lorelei', 'date': future.isoformat(), 'info': 'Tour',
                  'ticket_url': 'https://www.eventim.de/sting'},
                 {'artist': 'Sting', 'venue': 'Seebühne Bregenz', 'date': future.isoformat(), 'info': 'x',
                  'country': 'Österreich'},
                 {'artist': 'Sting', 'venue': 'Arena di Verona', 'date': future.isoformat(), 'info': 'x'}, kind='event')
        lorelei, bregenz, verona = (Suggestion.objects.get(kind='event', name__contains=n)
                                    for n in ('Lorelei', 'Bregenz', 'Verona'))
        r = self.client.get('/leisure/new_events')
        self.assertContains(r, 'Neue Konzerte')
        self.assertContains(r, 'neue Venue')
        self.assertContains(r, '🎟 Tickets')

        r = self.client.post('/leisure/new_events', {f'verdict_{lorelei.pk}': 'up', f'verdict_{bregenz.pk}': 'up',
                                                     f'verdict_{verona.pk}': 'down'}, follow=True)
        self.assertContains(r, 'zuerst unter Neue Venues')
        event = UpcomingEvent.objects.get(venue__name='Lorelei', date=future)
        self.assertEqual((event.artist.name, event.info, event.ticket_url), ('Sting', 'Tour', 'https://www.eventim.de/sting'))
        self.assertEqual(Suggestion.objects.get(pk=bregenz.pk).status, Suggestion.Status.PENDING)
        self.assertEqual(Suggestion.objects.get(pk=verona.pk).status, Suggestion.Status.REJECTED)

        venue = Suggestion.objects.get(kind='venue', name='Seebühne Bregenz')
        self.client.post('/leisure/new_venues', {f'verdict_{venue.pk}': 'up', f'rating_{venue.pk}': '8'})
        self.client.post('/leisure/new_events', {f'verdict_{bregenz.pk}': 'up'})
        self.assertTrue(UpcomingEvent.objects.filter(venue__name='Seebühne Bregenz', date=future).exists())
        task = Task.objects.get(name='Vorschläge für weitere Upcoming Events machen')
        self.assertEqual((task.executor, task.interval_hours), (Task.Executor.CLOUD, 168))
        self.assertIn('/leisure/new_events', task.prompt)

    def test_event_voting(self):
        future = datetime.date.today() + datetime.timedelta(days=100)
        self.add({'artist': 'Sting', 'venue': 'Lorelei', 'date': future.isoformat(), 'info': 'Tour'},
                 {'artist': 'Sting', 'venue': 'Arena di Verona', 'date': future.isoformat(), 'info': 'x'},
                 {'artist': 'Sting', 'venue': 'Seebühne Bregenz', 'date': future.isoformat(), 'info': 'x',
                  'country': 'Österreich'}, kind='event')
        lorelei, verona, bregenz = (Suggestion.objects.get(kind='event', name__contains=n)
                                    for n in ('Lorelei', 'Verona', 'Bregenz'))
        Suggestion.objects.filter(pk=verona.pk).update(status='rejected')
        Suggestion.objects.create(kind='event', name='Alt', payload={'artist': 'Sting', 'venue': 'Lorelei',
                                                                     'date': '2020-01-01'})

        r = self.client.get('/leisure/new_events/voting')  # ohne Login
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Lorelei')
        self.assertContains(r, 'Seebühne Bregenz')
        self.assertNotContains(r, '@ Arena di Verona')  # verworfen
        self.assertNotContains(r, '2020')  # vergangen
        self.assertContains(r, ('Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag')[
            (datetime.date.today() + datetime.timedelta(days=100)).weekday()])

        r = self.client.post('/leisure/new_events/voting', {'action': 'save', 'name': '  ', f'vote_{lorelei.pk}': 'up'},
                             follow=True)
        self.assertContains(r, 'Namen eintragen')
        self.assertFalse(EventVote.objects.exists())

        self.client.post('/leisure/new_events/voting', {
            'action': 'save', 'name': ' Anna  Maria ', f'vote_{lorelei.pk}': 'up',
            f'comment_{bregenz.pk}': 'nette Idee, aber Termin passt nicht', f'vote_{verona.pk}': 'up'})
        self.assertEqual(sorted(EventVote.objects.values_list('name', 'vote', 'comment')),
                         [('Anna Maria', '', 'nette Idee, aber Termin passt nicht'), ('Anna Maria', 'up', '')])

        # gleicher Name (andere Schreibweise) überschreibt, leer löscht
        self.client.post('/leisure/new_events/voting', {'action': 'save', 'name': 'anna maria',
                                                        f'vote_{lorelei.pk}': 'neutral', f'comment_{lorelei.pk}': 'mal sehen'})
        self.assertEqual(list(EventVote.objects.values_list('suggestion', 'vote', 'comment')),
                         [(lorelei.pk, 'neutral', 'mal sehen')])

        self.client.post('/leisure/new_events/voting', {'action': 'save', 'name': 'Ben', f'vote_{lorelei.pk}': 'down'})
        r = self.client.get('/leisure/new_events/voting')  # Session merkt sich Ben
        self.assertContains(r, 'value="Ben"')
        self.assertContains(r, 'anna maria')
        self.assertContains(r, '👍 0 · 😐 1 · 👎 1')

        self.client.force_login(User.objects.create_superuser('admin', password='pw'))
        r = self.client.get('/leisure/new_events')
        self.assertContains(r, 'Freunde: 👍 0 · 😐 1 · 👎 1')
        self.assertContains(r, '/leisure/new_events/voting')


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class LeisureIndexTests(TestCase):
    def test_anonymous_sees_only_voting(self):
        response = self.client.get('/leisure/')
        self.assertContains(response, 'href="/leisure/new_events/voting"')
        self.assertNotContains(response, 'href="/leisure/new_events"')

    def test_staff_sees_tiles_with_counts(self):
        Suggestion.objects.create(kind=Suggestion.Kind.EVENT, name='Sting @ Arena di Verona, 2099-07-14',
                                  payload={'artist': 'Sting', 'venue': 'Arena di Verona', 'date': '2099-07-14'})
        self.client.force_login(User.objects.create_user('staff', password='x', is_staff=True))
        response = self.client.get('/leisure/')
        self.assertContains(response, 'href="/leisure/new_events"')
        self.assertContains(response, 'href="/admin/leisure/artist/"')
        self.assertContains(response, 'Neue Konzerte <span class="badge text-bg-primary">1</span>')
        self.assertNotContains(response, 'Neue Artists <span')
