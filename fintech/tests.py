import json
import re
from decimal import Decimal

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


@override_settings(MCP_READONLY_API_KEY='mcp-key', FINTECH_API_KEY='test-key')
class McpServerTests(TestCase):
    """Rein lesender MCP-Server unter /fintech/mcp (fintech.apis.mcp_server)."""

    def rpc(self, method, params=None, msg_id=1, token='mcp-key'):
        body = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if msg_id is not None:
            body['id'] = msg_id
        return self.client.post('/fintech/mcp', data=json.dumps(body), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_auth_only_with_mcp_key(self):
        r = self.client.post('/fintech/mcp', data='{}', content_type='application/json')
        self.assertEqual(r.status_code, 401)
        self.assertIn('Bearer', r['WWW-Authenticate'])
        # FINTECH_API_KEY öffnet den MCP-Server nicht, egal in welchem Header
        self.assertEqual(self.rpc('ping', token='test-key').status_code, 401)
        r = self.client.post('/fintech/mcp', data='{}', content_type='application/json', HTTP_X_API_KEY='test-key')
        self.assertEqual(r.status_code, 401)
        # Admin-Session ebenfalls nicht
        self.client.force_login(User.objects.create_user('littlecapa', password='pw', is_staff=True))
        r = self.client.post('/fintech/mcp', data='{}', content_type='application/json')
        self.assertEqual(r.status_code, 401)

    @override_settings(MCP_READONLY_API_KEY=None)
    def test_unset_key_blocks_everything(self):
        self.assertEqual(self.rpc('ping', token='').status_code, 401)
        self.assertEqual(self.rpc('ping', token='None').status_code, 401)

    def test_mcp_key_does_not_open_other_endpoints(self):
        for path in ('/fintech/api/portfolio', '/fintech/api/watchlist', '/fintech/export'):
            for headers in ({'HTTP_AUTHORIZATION': 'Bearer mcp-key'}, {'HTTP_X_API_KEY': 'mcp-key'}):
                r = self.client.get(path, **headers)
                self.assertIn(r.status_code, (302, 401, 403), f'{path} {headers}')

    def test_get_not_allowed(self):
        r = self.client.get('/fintech/mcp', HTTP_AUTHORIZATION='Bearer mcp-key')
        self.assertEqual(r.status_code, 405)

    def test_initialize_negotiates_version(self):
        result = self.rpc('initialize', {'protocolVersion': '2025-06-18'}).json()['result']
        self.assertEqual(result['protocolVersion'], '2025-06-18')
        self.assertIn('tools', result['capabilities'])
        result = self.rpc('initialize', {'protocolVersion': '1999-01-01'}).json()['result']
        self.assertEqual(result['protocolVersion'], '2025-11-25')

    def test_notification_returns_202(self):
        self.assertEqual(self.rpc('notifications/initialized', msg_id=None).status_code, 202)

    def test_tools_are_all_read_only(self):
        tools = self.rpc('tools/list').json()['result']['tools']
        self.assertGreaterEqual(len(tools), 7)
        for tool in tools:
            self.assertTrue(tool['annotations']['readOnlyHint'], tool['name'])
            self.assertTrue(re.match(r'^get_', tool['name']), tool['name'])

    def test_get_watchlist_with_filter(self):
        from fintech.models import Asset, Watchlist, WatchlistEntry
        user = User.objects.create_user('owner', password='pw')
        asset = Asset.objects.create(isin='US21873S1087', name='CoreWeave', current_price=Decimal('100'))
        for name in ('Neo Cloud Anbieter', 'Andere'):
            WatchlistEntry.objects.create(watchlist=Watchlist.objects.create(name=name, user=user), asset=asset)

        result = self.rpc('tools/call', {'name': 'get_watchlist', 'arguments': {}}).json()['result']
        self.assertFalse(result['isError'])
        self.assertEqual(result['structuredContent']['count'], 2)

        result = self.rpc('tools/call', {'name': 'get_watchlist',
                                         'arguments': {'watchlist': 'neo cloud anbieter'}}).json()['result']
        self.assertEqual(result['structuredContent']['count'], 1)
        self.assertEqual(json.loads(result['content'][0]['text'])['entries'][0]['isin'], 'US21873S1087')

    def test_tool_errors(self):
        result = self.rpc('tools/call', {'name': 'get_price_history', 'arguments': {'isin': 'kaputt'}}).json()['result']
        self.assertTrue(result['isError'])
        error = self.rpc('tools/call', {'name': 'get_price_history', 'arguments': {}}).json()['error']
        self.assertEqual(error['code'], -32602)
        error = self.rpc('tools/call', {'name': 'delete_everything'}).json()['error']
        self.assertEqual(error['code'], -32602)
        error = self.rpc('resources/list').json()['error']
        self.assertEqual(error['code'], -32601)
        r = self.client.post('/fintech/mcp', data='{kein json', content_type='application/json',
                             HTTP_AUTHORIZATION='Bearer mcp-key')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error']['code'], -32700)


class CurrencyProxySarTests(TestCase):
    def test_sar_uses_usd_peg(self):
        from datetime import datetime, timezone
        from fintech.apis.services.exchange_rate_proxy import CurrencyProxy
        proxy = CurrencyProxy()
        proxy._data, proxy._fetched_at = {'rates': {'USD': '1.1'}}, datetime.now(timezone.utc)
        self.assertEqual(proxy.get_rate('SAR'), Decimal('4.125'))
