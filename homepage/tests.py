from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .menu import ACCESS_CHECKS, SECTIONS


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MenuTests(TestCase):
    def test_all_entries_resolve(self):
        for _, entries in SECTIONS:
            for url_name, _, _, _, access in entries:
                reverse(url_name)
                self.assertIn(access, ACCESS_CHECKS)

    def test_anonymous_sees_only_public_areas(self):
        response = self.client.get('/menue/')
        self.assertContains(response, 'href="/leisure/"')
        self.assertContains(response, 'href="/bordkasse/"')
        self.assertContains(response, 'href="/fintech/"')
        self.assertNotContains(response, 'href="/tasks/"')
        self.assertContains(response, 'Anmelden')

    def test_staff_sees_everything_but_superuser_pages(self):
        user = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(user)
        response = self.client.get('/menue/')
        self.assertContains(response, 'href="/fintech/"')
        self.assertContains(response, 'href="/tasks/"')
        self.assertNotContains(response, 'href="/monitoring/"')
        self.assertNotContains(response, 'Anmelden')


    def test_nav_menu_link_only_for_logged_in_users(self):
        for url in ('/', '/jugendschach/', '/links/'):
            self.assertNotContains(self.client.get(url), 'href="/menue/"')
        self.client.force_login(User.objects.create_user('member', password='x'))
        self.assertContains(self.client.get('/jugendschach/'), 'href="/menue/"')

@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class JugendschachTests(TestCase):
    def test_overview_is_public_and_shows_all_rows(self):
        response = self.client.get('/jugendschach/')
        self.assertEqual(response.status_code, 200)
        for text in ('Jugendschachtraining', '5. Mannschaft', 'U16-Mannschaft', 'Vereinsinfo',
                     'href="/jugendschach/training/"'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'Link folgt')
        self.assertNotContains(response, 'Vereins-Homepage')

    def test_header_with_contact_on_both_pages(self):
        from .jugendschach import CLUB_HOMEPAGE, JUGEND_MAIL
        for url in ('/jugendschach/', '/jugendschach/training/'):
            response = self.client.get(url)
            self.assertContains(response, 'scbb_logo')
            self.assertContains(response, f'href="mailto:{JUGEND_MAIL}"')
            self.assertContains(response, f'href="{CLUB_HOMEPAGE}"')

    def test_team_and_club_links(self):
        from .jugendschach import CLUB_TILES, TEAMS
        response = self.client.get('/jugendschach/')
        for tile in [t for team in TEAMS for t in team['tiles']] + CLUB_TILES:
            self.assertContains(response, tile['url'].replace('&', '&amp;'))

    def test_training_page_shows_flyer_details(self):
        response = self.client.get('/jugendschach/training/')
        self.assertEqual(response.status_code, 200)
        for text in ('Jeden Dienstag, 17–19 Uhr', 'An der Wolfsburg 1, 53225 Bonn', 'Flyer öffnen'):
            self.assertContains(response, text)

    def test_listed_in_menu(self):
        self.assertContains(self.client.get('/menue/'), 'href="/jugendschach/"')
