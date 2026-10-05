"""Routing isolation and fail-closed proxy validation; no paid/provider calls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_network import LocalProxyRoutes


class RoutesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'provider-network.json'
        self.handler = LocalProxyRoutes(lambda: self.config)
        system_patch = patch('urllib.request.getproxies', return_value={})
        self.system = system_patch.start()
        self.addCleanup(system_patch.stop)
        bypass_patch = patch('urllib.request.proxy_bypass', return_value=False)
        self.bypass = bypass_patch.start()
        self.addCleanup(bypass_patch.stop)

    def configure(self, proxy='http://127.0.0.1:7890'):
        self.config.write_text(json.dumps({'https_proxy_by_host': {
            'relay.example': proxy, '127.0.0.1': proxy}}), encoding='utf-8')

    def test_no_system_proxy_stays_direct(self):
        request = urllib.request.Request('https://relay.example/v1/models')
        self.assertIsNone(self.handler.route(request))
        self.configure()
        self.assertIsNone(self.handler.route(urllib.request.Request('https://other.example/v1/models')))
        self.assertIsNone(self.handler.route(urllib.request.Request('http://127.0.0.1:8786/api/health')))
        self.assertIsNone(self.handler.route(urllib.request.Request('https://127.0.0.1/health')))

    def test_system_proxy_applies_to_unconfigured_external_hosts(self):
        self.system.return_value = {'https': 'http://127.0.0.1:9999'}
        request = urllib.request.Request('https://relay.example/v1/models')
        self.assertEqual(self.handler.route(request), 'http://127.0.0.1:9999')
        self.configure()
        self.assertEqual(self.handler.route(request), 'http://127.0.0.1:7890')
        self.assertEqual(self.handler.route(urllib.request.Request('https://other.example/models')), 'http://127.0.0.1:9999')

    def test_loopback_never_uses_proxy_even_without_bypass_list(self):
        self.system.return_value = {'https': 'http://127.0.0.1:9999'}
        self.configure()
        for host in ('localhost', 'LOCALHOST.', '127.0.0.1', '127.0.0.2', '[::1]'):
            for scheme in ('http', 'https'):
                with self.subTest(host=host, scheme=scheme):
                    self.assertIsNone(self.handler.route(urllib.request.Request(f'{scheme}://{host}:8188/models')))
        self.system.assert_not_called()

    def test_system_bypass_and_runtime_changes_are_respected(self):
        request = urllib.request.Request('https://relay.example:443/v1/models')
        self.system.return_value = {'https': 'http://127.0.0.1:7890'}
        self.assertEqual(self.handler.route(request), 'http://127.0.0.1:7890')
        self.system.return_value = {'https': 'http://127.0.0.1:7891'}
        self.assertEqual(self.handler.route(request), 'http://127.0.0.1:7891')
        self.bypass.return_value = True
        self.assertIsNone(self.handler.route(request))
        self.bypass.assert_called_with('relay.example:443')

    def test_explicit_direct_mode_keeps_specific_routes(self):
        self.configure()
        config = json.loads(self.config.read_text())
        config['use_system_proxy'] = False
        self.config.write_text(json.dumps(config))
        self.system.return_value = {'https': 'http://127.0.0.1:9999'}
        self.assertIsNone(self.handler.route(urllib.request.Request('https://other.example/models')))
        self.assertEqual(self.handler.route(urllib.request.Request('https://relay.example/models')), 'http://127.0.0.1:7890')
        self.system.assert_not_called()

    def test_invalid_config_never_silently_falls_back(self):
        for raw in ('not-json', '[]', '{"use_system_proxy":"false"}', '{"https_proxy_by_host":[]}'):
            self.config.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(urllib.error.URLError):
                self.handler.route(urllib.request.Request('https://relay.example/models'))
        self.system.assert_not_called()

    def test_unsupported_system_proxy_is_reported_without_credentials(self):
        for proxy in ('socks5://user:private@127.0.0.1:7890', 'http://:7890', 'http://127.0.0.1:bad'):
            self.system.return_value = {'https': proxy}
            with self.subTest(proxy=proxy), self.assertRaises(urllib.error.URLError) as raised:
                self.handler.route(urllib.request.Request('https://relay.example/models'))
            self.assertNotIn('private', str(raised.exception))
            self.assertIn('系统 HTTPS 代理', str(raised.exception))

    def test_real_connect_failure_uses_proxy_once_and_sends_no_origin_key(self):
        calls = []
        class Proxy(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_CONNECT(self):
                calls.append((self.path, dict(self.headers)))
                self.send_error(502, 'Fixture tunnel unavailable')
        proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        self.system.return_value = {'https': f'http://127.0.0.1:{proxy.server_port}'}
        import providers
        import model_catalog
        p = {'base_url': 'https://unresolvable.invalid/v1', 'protocol': 'openai_chat', 'secret': ''}
        # Exercise the actual shared opener used by discovery and generation.
        with patch.object(providers, 'OPENER', urllib.request.build_opener(self.handler, providers.NoRedirect())), \
                patch.object(providers, 'headers', return_value={'Authorization': 'Bearer fixture-origin-key'}):
            with self.assertRaises(providers.ProviderError):
                providers.request(p, '/chat/completions', {'model': 'fixture', 'messages': []})
            with self.assertRaises(providers.ProviderError):
                model_catalog._request(p, '/models', 'fixture-origin-key', 3)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(host == 'unresolvable.invalid:443' for host, _ in calls))
        self.assertTrue(all('Authorization' not in headers for _, headers in calls))

    def test_exact_host_and_https_only(self):
        self.configure()
        self.assertEqual(self.handler.route(urllib.request.Request('https://RELAY.example/v1/models')), 'http://127.0.0.1:7890')
        for url in ('https://relay.example.evil/models', 'https://child.relay.example/models', 'http://relay.example/models'):
            self.assertIsNone(self.handler.route(urllib.request.Request(url)))

    def test_remote_credential_and_malformed_proxies_rejected(self):
        for value in ('http://proxy.example:8080', 'http://10.0.0.2:8080', 'http://user:password@127.0.0.1:7890',
                      'https://127.0.0.1:7890', 'http://127.0.0.1:7890/path', 'http://127.0.0.1:7890?key=x',
                      'http://127.0.0.1', 'http://localhost:7890'):
            with self.subTest(value=value):
                self.configure(value)
                with self.assertRaises(urllib.error.URLError):
                    self.handler.route(urllib.request.Request('https://relay.example/models'))

    def test_proxy_failure_never_retries_direct_or_reposts(self):
        self.configure()
        request = urllib.request.Request('https://relay.example/v1/responses', data=b'fixture-only')
        with patch.object(self.handler, 'proxy_open', side_effect=urllib.error.URLError('offline')) as open_proxy:
            with self.assertRaises(urllib.error.URLError):
                self.handler.https_open(request)
        open_proxy.assert_called_once_with(request, 'http://127.0.0.1:7890', 'https')


if __name__ == '__main__':
    unittest.main()
