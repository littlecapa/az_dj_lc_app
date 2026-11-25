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


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class JugendschachTests(TestCase):
    def test_page_is_public_and_shows_all_rows(self):
        response = self.client.get('/jugendschach/')
        self.assertEqual(response.status_code, 200)
        for text in ('Jugendschachtraining', '5. Mannschaft', 'U16-Mannschaft', 'Vereinsinfo',
                     'Jeden Dienstag, 17–19 Uhr', 'An der Wolfsburg 1, 53225 Bonn'):
            self.assertContains(response, text)

    def test_club_links_and_pending_links(self):
        from .jugendschach import CLUB_HOMEPAGE, DRIVE_AUFNAHMEANTRAG, DRIVE_LEITFADEN_MF
        response = self.client.get('/jugendschach/')
        for url in (CLUB_HOMEPAGE, DRIVE_AUFNAHMEANTRAG, DRIVE_LEITFADEN_MF):
            self.assertContains(response, f'href="{url}"')
        self.assertContains(response, 'Link folgt', count=4)

    def test_listed_in_menu(self):
        self.assertContains(self.client.get('/menue/'), 'href="/jugendschach/"')
