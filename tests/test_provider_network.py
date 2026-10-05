"""Routing isolation and fail-closed proxy validation; no paid/provider calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
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

    def configure(self, proxy='http://127.0.0.1:7890'):
        self.config.write_text(json.dumps({'https_proxy_by_host': {
            'relay.example': proxy, '127.0.0.1': proxy}}), encoding='utf-8')

    def test_default_and_other_connections_remain_direct(self):
        request = urllib.request.Request('https://relay.example/v1/models')
        with patch.dict('os.environ', {'HTTPS_PROXY': 'http://127.0.0.1:9999'}):
            self.assertIsNone(self.handler.route(request))
        self.configure()
        self.assertIsNone(self.handler.route(urllib.request.Request('https://other.example/v1/models')))
        self.assertIsNone(self.handler.route(urllib.request.Request('http://127.0.0.1:8786/api/health')))
        self.assertIsNone(self.handler.route(urllib.request.Request('https://127.0.0.1/health')))

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
