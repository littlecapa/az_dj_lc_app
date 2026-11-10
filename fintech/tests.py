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


class WatchlistLinkTests(TestCase):
    def test_link_button_only_when_set(self):
        from fintech.models import Watchlist
        admin = User.objects.create_superuser('admin', password='pw')
        self.client.force_login(admin)
        wl = Watchlist.objects.create(name='AAA Zertifikate', user=admin)
        url = '/fintech/watchlist-performance/AAA Zertifikate/'
        self.assertNotContains(self.client.get(url), 'Rechner öffnen')
        wl.link = 'https://docs.google.com/spreadsheets/d/abc'
        wl.save()
        self.assertContains(self.client.get(url), 'href="https://docs.google.com/spreadsheets/d/abc"')


class PriceFetchFailureTicketTests(TestCase):
    def test_no_ticket_for_lookthrough_placeholders(self):
        from unittest import mock
        from fintech.models import Asset, Holdings, Watchlist, WatchlistEntry
        from fintech.services import report_price_fetch_failures

        def asset(isin, quantity=None):
            a = Asset.objects.create(isin=isin, name=isin, asset_class='STOCK')
            if quantity is not None:
                Holdings.objects.create(asset=a, quantity=Decimal(quantity), average_purchase_price=Decimal('0'))
            return a

        asset('XS3104481257', '0')  # Anleihe nur über einen Fonds
        asset('DE0005140008', '5')  # eigener Bestand
        watched = asset('US00724F1012')
        wl = Watchlist.objects.create(name='Test', user=User.objects.create_user('u'))
        WatchlistEntry.objects.create(watchlist=wl, asset=watched)
        failures = [{'isin': i, 'name': i, 'asset_class': 'STOCK', 'error': 'kein Kurs'}
                    for i in ('XS3104481257', 'DE0005140008', 'US00724F1012')]

        with mock.patch('fintech.services.JiraClient') as jira:
            report_price_fetch_failures(failures[:1])
            jira.assert_not_called()
            report_price_fetch_failures(failures)
            description = jira.return_value.create_issue.call_args.kwargs['description']
        self.assertIn('DE0005140008', description)
        self.assertIn('US00724F1012', description)
        self.assertNotIn('XS3104481257', description)


class IsinChangeTests(TestCase):
    """ISIN-Wechsel (fintech/isin_change.py, Command change_isin, Seite /fintech/isin-change/)."""

    OLD, NEW = 'DE000PFSE212', 'DE000PFSE253'

    def setUp(self):
        from django.utils import timezone
        from fintech.models import (
            Asset, FondHolding, Holdings, NewsEvent, Price, PriceAlarm, Watchlist, WatchlistEntry,
        )
        self.user = User.objects.create_user('littlecapa', password='pw', is_staff=True)
        self.asset = Asset.objects.create(
            isin=self.OLD, wkn='PFSE21', symbol='XETR-PFSE', name='Pfisterer Holding',
            price_fetch_blocked=True, price_fetch_failing_since=timezone.now(),
        )
        self.other = Asset.objects.create(isin='DE0007164600', wkn='716460', name='SAP')
        self.fund = Asset.objects.create(isin='IE00B4L5Y983', name='MSCI World', asset_class='ETF')
        Holdings.objects.create(asset=self.asset, quantity=Decimal('30'), average_purchase_price=Decimal('62.80'))
        Price.objects.create(asset=self.asset, current_price=Decimal('67.85'), timestamp=timezone.now())
        Price.objects.create(asset=self.other, current_price=Decimal('210'), timestamp=timezone.now())
        watchlist = Watchlist.objects.create(name='Test', user=self.user)
        WatchlistEntry.objects.create(watchlist=watchlist, asset=self.asset)
        PriceAlarm.objects.create(asset=self.asset, target_price=Decimal('80'))
        FondHolding.objects.create(fund=self.fund, holding=self.asset, percentage=Decimal('1.5'))
        event = NewsEvent.objects.create(event_type='new_high', new_value=Decimal('70'))
        event.assets.add(self.asset, self.other)

    def patch_lookups(self, figi='XETR-PFSE', yahoo=None, price=Decimal('68.00'), wkn=None):
        """Externe Abfragen ersetzen; yahoo = {isin: symbol}."""
        from unittest import mock
        from fintech import isin_change
        yahoo = yahoo or {}
        pm = mock.Mock()
        pm.isin2price.return_value = price
        pm.isin2wkn.return_value = wkn
        patches = [
            mock.patch.object(isin_change, '_lookup_tradingview_symbol', return_value=figi),
            mock.patch.object(isin_change, '_lookup_yahoo_symbol', side_effect=lambda isin: yahoo.get(isin)),
            mock.patch.object(isin_change, '_provider_manager', return_value=pm),
            mock.patch('fintech.services._provider_manager', pm),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return pm

    def test_moves_everything_and_deletes_old(self):
        from fintech.isin_change import change_isin
        from fintech.models import (
            Asset, FondHolding, Holdings, NewsEvent, Price, PriceAlarm, WatchlistEntry,
        )
        created_at = self.asset.created_at
        result = change_isin(self.OLD.lower(), f' {self.NEW} ')

        self.assertFalse(Asset.objects.filter(pk=self.OLD).exists())
        new = Asset.objects.get(pk=self.NEW)
        self.assertEqual((new.name, new.symbol), ('Pfisterer Holding', 'XETR-PFSE'))
        self.assertEqual(new.current_price, Decimal('67.85'))
        self.assertEqual(new.created_at, created_at)
        self.assertIsNone(new.wkn)
        # Der blockierte Kurs-Abruf galt der alten ISIN
        self.assertFalse(new.price_fetch_blocked)
        self.assertIsNone(new.price_fetch_failing_since)

        self.assertEqual(Holdings.objects.get(asset=new).quantity, Decimal('30'))
        self.assertEqual(Price.objects.filter(asset=new).count(), 1)
        self.assertEqual(WatchlistEntry.objects.filter(asset=new).count(), 1)
        self.assertEqual(PriceAlarm.objects.filter(asset=new).count(), 1)
        self.assertEqual(FondHolding.objects.get(fund=self.fund).holding_id, self.NEW)
        self.assertEqual(set(NewsEvent.objects.get().assets.values_list('isin', flat=True)), {self.NEW, 'DE0007164600'})
        # Fremde Daten bleiben unberührt
        self.assertEqual(Price.objects.filter(asset=self.other).count(), 1)
        self.assertEqual(result.total_moved, 6)

    def test_dry_run_changes_nothing(self):
        from fintech.isin_change import change_isin
        from fintech.models import Asset, Holdings
        result = change_isin(self.OLD, self.NEW, dry_run=True)
        self.assertEqual(result.total_moved, 6)
        self.assertFalse(Asset.objects.filter(pk=self.NEW).exists())
        old = Asset.objects.get(pk=self.OLD)
        self.assertEqual(old.wkn, 'PFSE21')
        self.assertTrue(old.price_fetch_blocked)
        self.assertEqual(Holdings.objects.get().asset_id, self.OLD)

    def test_invalid_input_is_rejected(self):
        from fintech.isin_change import IsinChangeError, change_isin
        from fintech.models import Asset
        for old, new in (
            ('kaputt', self.NEW), (self.OLD, 'DE123'), (self.OLD, self.OLD),
            ('DE0000000000', self.NEW),      # altes Asset unbekannt
            (self.OLD, 'DE0007164600'),      # neue ISIN schon vergeben
        ):
            with self.assertRaises(IsinChangeError, msg=f'{old} → {new}'):
                change_isin(old, new)
        self.assertEqual(Asset.objects.count(), 3)
        self.assertEqual(Asset.objects.get(pk=self.OLD).wkn, 'PFSE21')

    def test_holdings_reference_follows(self):
        from fintech.isin_change import change_isin
        from fintech.models import Asset
        Asset.objects.filter(pk=self.fund.pk).update(holdings_reference=self.asset)
        change_isin(self.OLD, self.NEW)
        self.assertEqual(Asset.objects.get(pk=self.fund.pk).holdings_reference_id, self.NEW)

    def test_attributes_set_automatically(self):
        from fintech.isin_change import change_isin, needs_manual_review, refresh_attributes
        from fintech.models import Asset, Price
        self.patch_lookups(figi='XETR-PFSE', yahoo={self.NEW: 'PFSE.DE'})
        change_isin(self.OLD, self.NEW)
        attributes = refresh_attributes(self.OLD, self.NEW)
        new = Asset.objects.get(pk=self.NEW)
        self.assertEqual(new.wkn, 'PFSE25')       # aus der deutschen ISIN abgeleitet
        self.assertEqual(new.symbol, 'XETR-PFSE')
        self.assertIsNone(new.yahoo_symbol)        # Yahoo findet die neue ISIN, kein Override nötig
        self.assertEqual(new.current_price, Decimal('68.00'))
        self.assertEqual(Price.objects.filter(asset=new).count(), 2)
        self.assertFalse(needs_manual_review(attributes))

    def test_yahoo_falls_back_to_old_ticker(self):
        from fintech.isin_change import change_isin, refresh_attributes
        from fintech.models import Asset
        pm = self.patch_lookups(yahoo={self.OLD: 'PFSE.DE'})
        change_isin(self.OLD, self.NEW)
        refresh_attributes(self.OLD, self.NEW)
        self.assertEqual(Asset.objects.get(pk=self.NEW).yahoo_symbol, 'PFSE.DE')
        self.assertEqual(pm.isin2price.call_args.kwargs['yahoo_symbol'], 'PFSE.DE')

    def test_unresolved_attributes_need_review(self):
        from fintech.isin_change import MANUAL, change_isin, needs_manual_review, refresh_attributes
        from fintech.models import Asset
        self.patch_lookups(figi=None, price=None)
        change_isin(self.OLD, self.NEW)
        attributes = refresh_attributes(self.OLD, self.NEW)
        self.assertTrue(needs_manual_review(attributes))
        status = {a.label: a.status for a in attributes}
        self.assertEqual(status['Symbol (TradingView)'], MANUAL)
        self.assertEqual(status['Yahoo-Symbol'], MANUAL)
        self.assertEqual(status['Kurs'], MANUAL)
        self.assertEqual(Asset.objects.get(pk=self.NEW).symbol, 'XETR-PFSE')  # altes Symbol bleibt stehen

    def test_dry_run_attributes_save_nothing(self):
        from fintech.isin_change import refresh_attributes
        from fintech.models import Asset, Price
        self.patch_lookups(figi='XETR-NEU', yahoo={self.OLD: 'PFSE.DE'})
        attributes = refresh_attributes(self.OLD, self.NEW, dry_run=True)
        self.assertEqual({a.label: a.new for a in attributes}['WKN'], 'PFSE25')
        old = Asset.objects.get(pk=self.OLD)
        self.assertEqual((old.wkn, old.symbol, old.yahoo_symbol), ('PFSE21', 'XETR-PFSE', None))
        self.assertEqual(Price.objects.filter(asset=old).count(), 1)

    def test_command(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from fintech.models import Asset
        self.patch_lookups(yahoo={self.NEW: 'PFSE.DE'})
        out = StringIO()
        call_command('change_isin', self.OLD, self.NEW, '--dry-run', stdout=out)
        self.assertIn('[Dry-Run]', out.getvalue())
        self.assertTrue(Asset.objects.filter(pk=self.OLD).exists())
        call_command('change_isin', self.OLD, self.NEW, stdout=out)
        self.assertEqual(Asset.objects.get(pk=self.NEW).wkn, 'PFSE25')
        with self.assertRaises(CommandError):
            call_command('change_isin', self.OLD, self.NEW, stdout=out)

    def test_page(self):
        from fintech.models import Asset
        self.patch_lookups(figi=None, yahoo={self.NEW: 'PFSE.DE'})
        self.client.force_login(self.user)
        url = '/fintech/isin-change/'
        self.assertContains(self.client.get(url), 'Alte ISIN')
        self.assertContains(self.client.get('/fintech/'), url)

        r = self.client.post(url, {'old_isin': self.OLD, 'new_isin': self.NEW, 'dry_run': 'on'})
        self.assertContains(r, 'Dry-Run – es wurde nichts gespeichert')
        self.assertContains(r, 'Jetzt ausführen')
        self.assertTrue(Asset.objects.filter(pk=self.OLD).exists())

        r = self.client.post(url, {'old_isin': self.OLD, 'new_isin': self.NEW})
        self.assertContains(r, 'ISIN-Wechsel ausgeführt')
        # Symbol ließ sich nicht automatisch klären → Link auf Change Asset der NEUEN ISIN
        self.assertContains(r, f'/admin/fintech/asset/{self.NEW}/change/')
        self.assertFalse(Asset.objects.filter(pk=self.OLD).exists())

        r = self.client.post(url, {'old_isin': self.OLD, 'new_isin': self.NEW})
        self.assertContains(r, 'Nicht ausgeführt')
