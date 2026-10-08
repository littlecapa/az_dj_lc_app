import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver

from fintech import urls as fintech_urls

SAMPLE_ARGS = {'str': 'DE0005140008', 'slug': 'aktien', 'path': 'test', 'int': '1'}


def _walk(patterns, prefix):
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield re.sub(r'<(?:(\w+):)?\w+>', lambda m: SAMPLE_ARGS[m.group(1) or 'str'], route)


FINTECH_PATHS = sorted(set(_walk(fintech_urls.urlpatterns, '/fintech/')))


@override_settings(FINTECH_API_KEY='test-key')
class FintechAdminOnlyTests(TestCase):
    """Jede URL unter /fintech/ darf nur mit Admin-Login (is_staff) oder API-Key etwas liefern."""

    def assert_blocked(self, path, method, response):
        allowed = {401, 403, 405}
        if response.status_code == 302:
            self.assertRegex(response['Location'], r'/(admin|accounts)/login/', f'{method} {path}')
        else:
            self.assertIn(response.status_code, allowed, f'{method} {path} ist ohne Admin erreichbar')

    def check_all(self):
        self.assertGreater(len(FINTECH_PATHS), 40)
        for path in FINTECH_PATHS:
            for method in ('get', 'post', 'patch', 'delete'):
                response = getattr(self.client, method)(path)
                self.assert_blocked(path, method.upper(), response)

    def test_anonymous_blocked_everywhere(self):
        self.check_all()

    def test_logged_in_non_staff_blocked_everywhere(self):
        self.client.force_login(User.objects.create_user('crew', password='pw'))
        self.check_all()

    def test_wrong_api_key_blocked(self):
        r = self.client.get('/fintech/api/securities/DE0005140008/price', HTTP_X_API_KEY='falsch')
        self.assertEqual(r.status_code, 401)

    def test_staff_gets_through(self):
        self.client.force_login(User.objects.create_user('littlecapa', password='pw', is_staff=True))
        self.assertEqual(self.client.get('/fintech/backup/').status_code, 200)
        self.assertEqual(self.client.get('/fintech/api/news').status_code, 200)
