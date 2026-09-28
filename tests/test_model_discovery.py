"""Read-only discovery acceptance with real loopback HTTP and isolated storage."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_catalog
import providers
import server
import storage

KEY = 'fixture-only-discovery-not-a-real-key'
CALLS = []


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, payload, code=200, extra=None):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        CALLS.append({'path': self.path, 'headers': dict(self.headers), 'method': 'GET'})
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == '/openai/models':
            if 'after' not in query:
                return self.send({'data': [{'id': 'gpt-fixture-chat'}], 'has_more': True,
                                  'last_id': 'gpt-fixture-chat', 'next': 'https://evil.invalid/steal'})
            return self.send({'data': [{'id': 'gpt-fixture-chat'}, {'id': 'gpt-image-1'},
                                      {'id': 'sora-2'}, {'id': 'text-embedding-fixture'},
                                      {'id': 'qwen-image'}, {'id': 'glm-image'}, {'id': 'grok-imagine-video'},
                                      {'id': 'unrecognized-id', 'base_url': 'https://evil.invalid'}], 'has_more': False})
        if parsed.path == '/anthropic/v1/models':
            if 'after_id' not in query:
                return self.send({'data': [{'id': 'claude-fixture-a', 'display_name': 'Claude Fixture A'}],
                                  'has_more': True, 'last_id': 'claude-fixture-a'})
            return self.send({'data': [{'id': 'claude-fixture-b'}], 'has_more': False})
        if parsed.path == '/gemini/v1beta/models':
            if 'pageToken' not in query:
                return self.send({'models': [{'name': 'models/gemini-fixture', 'displayName': 'Gemini Fixture',
                                              'supportedGenerationMethods': ['generateContent']}], 'nextPageToken': 'next/&?'})
            return self.send({'models': [{'name': 'models/gemini-3-image-fixture', 'supportedGenerationMethods': ['generateContent']},
                                        {'name': 'models/embedding-fixture', 'supportedGenerationMethods': ['embedContent']},
                                        {'name': 'models/veo-fixture', 'supportedGenerationMethods': ['predictLongRunning']}]})
        if parsed.path == '/cursor/models':
            return self.send({'data': [{'id': 'page-' + query.get('cursor', ['first'])[0]}],
                              **({} if 'cursor' in query else {'next_cursor': 'cursor/&?'})})
        if parsed.path == '/loop/models':
            return self.send({'data': [{'id': 'repeated'}], 'has_more': True, 'last_id': 'repeated'})
        if parsed.path == '/empty/models':
            return self.send({'data': [], 'models': [{'id': 'must-not-use-fallback'}]})
        if parsed.path == '/badshape/models':
            return self.send({'data': {'id': 'not-an-array'}})
        if parsed.path == '/missing/models':
            return self.send({'message': 'no model list'})
        if parsed.path == '/allbad/models':
            return self.send({'data': [{'id': 123}, None, {'id': ''}]})
        if parsed.path == '/mixed/models':
            return self.send({'data': [{'id': 'gpt-valid'}, {'id': 123}, {'id': ''}]})
        if parsed.path == '/large/models':
            return self.send({'data': [{'id': 'gpt-valid', 'description': 'x' * 5000}]})
        if parsed.path == '/echo/models':
            return self.send({'data': [{'id': 'gpt-valid', 'name': 'name ' + KEY, 'description': 'Bearer ' + KEY},
                                      {'id': KEY}]})
        if parsed.path == '/error/models':
            return self.send({'error': {'message': 'denied ' + KEY}}, 401)
        if parsed.path == '/redirect/models':
            return self.send({}, 302, {'Location': f'http://127.0.0.1:{self.server.server_port}/redirect-target'})
        if parsed.path == '/custom/catalog':
            return self.send({'items': [{'id': 'gpt-custom-chat', 'name': 'Custom model'}]})
        if parsed.path == '/dual/custom-catalog':
            if self.headers.get('X-Catalog-Key') != 'Catalog ' + KEY or self.headers.get('Authorization'):
                return self.send({'error': {'message': 'wrong custom directory authentication'}}, 401)
            return self.send({'items': [{'id': 'gpt-dual-fixture'}]})
        if parsed.path == '/dual/models':
            if self.headers.get('Authorization') != 'Bearer ' + KEY or self.headers.get('X-Catalog-Key') or self.headers.get('X-Generation-Key'):
                return self.send({'error': {'message': 'wrong native directory authentication'}}, 401)
            return self.send({'data': [{'id': 'gpt-dual-fixture'}]})
        if parsed.path == '/single/models':
            return self.send({'data': [{'id': 'gpt-single'}]})
        return self.send({'error': {'message': 'not found'}}, 404)

    def do_POST(self):
        CALLS.append({'method': 'POST', 'path': self.path})
        self.send({'error': 'generation is forbidden in this fixture'}, 405)


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='guangyu-discovery-')
        cls.data_patch = patch.object(storage, 'DATA', Path(cls.temp.name))
        cls.data_patch.start()
        storage.init()
        cls.fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        cls.fixture.daemon_threads = True
        threading.Thread(target=cls.fixture.serve_forever, daemon=True).start()
        cls.upstream = f'http://127.0.0.1:{cls.fixture.server_port}'
        cls.app = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.app.daemon_threads = True
        cls.origin = f'http://127.0.0.1:{cls.app.server_port}'
        cls.port_patch = patch.object(server, 'PORT', cls.app.server_port)
        cls.origin_patch = patch.object(server, 'ORIGIN', cls.origin)
        cls.port_patch.start()
        cls.origin_patch.start()
        threading.Thread(target=cls.app.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown()
        cls.app.server_close()
        cls.fixture.shutdown()
        cls.fixture.server_close()
        cls.port_patch.stop()
        cls.origin_patch.stop()
        cls.data_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        CALLS.clear()
        with storage.connect() as conn:
            conn.execute('DELETE FROM providers')
            conn.execute('DELETE FROM jobs')
            conn.execute('DELETE FROM conversations')

    def api(self, path, body=None, status=200, headers=None):
        request_headers = {'Origin': self.origin, 'X-CSRF-Token': server.CSRF, 'Content-Type': 'application/json'}
        request_headers.update(headers or {})
        request = urllib.request.Request(self.origin + path,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                actual, raw = response.status, response.read()
        except urllib.error.HTTPError as ex:
            actual, raw = ex.code, ex.read()
        self.assertEqual(actual, status, raw.decode())
        value = json.loads(raw)
        self.assertNotIn(KEY, raw.decode())
        return value

    def config(self, path='/single', protocol='openai_chat', **kwargs):
        return {'platform': 'custom', 'kind': 'chat', 'protocol': protocol,
                'base_url': self.upstream + path, 'allow_local': True, 'api_key': KEY, **kwargs}

    def discover(self, path='/single', protocol='openai_chat', status=200, **kwargs):
        return self.api('/api/models/discover', self.config(path, protocol, **kwargs), status)

    def save(self, path='/single', **kwargs):
        return self.api('/api/providers/save', {**self.config(path), 'name': 'Fixture connection', 'model': 'gpt-fixture', **kwargs})

    def test_unsaved_openai_pagination_is_get_only_and_does_not_save(self):
        value = self.discover('/openai')
        self.assertEqual(value['pages'], 2)
        self.assertEqual(len(value['models']), 8)
        self.assertEqual(len(storage.items('providers')), 0)
        self.assertEqual(len(storage.items('jobs')), 0)
        self.assertTrue(all(call['method'] == 'GET' for call in CALLS))
        self.assertTrue(all(call['headers']['Authorization'] == 'Bearer ' + KEY for call in CALLS))
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(CALLS[1]['path']).query), {'after': ['gpt-fixture-chat']})
        self.assertTrue(all(item['base_url'] == self.upstream + '/openai' for item in value['models']))

    def test_native_image_video_and_unknown_kinds_are_conservative(self):
        entries = {item['id']: item for item in self.discover('/openai')['models']}
        self.assertEqual(entries['gpt-image-1']['protocol'], 'openai_image')
        self.assertEqual(entries['sora-2']['supported_kinds'], ['video'])
        for identity in ('text-embedding-fixture', 'qwen-image', 'glm-image', 'grok-imagine-video', 'unrecognized-id'):
            self.assertEqual(entries[identity]['supported_kinds'], [])
            self.assertIsNone(entries[identity]['protocol'])

    def test_anthropic_auth_and_pagination_use_native_contract(self):
        value = self.discover('/anthropic/v1', 'anthropic')
        self.assertEqual([item['id'] for item in value['models']], ['claude-fixture-a', 'claude-fixture-b'])
        headers = {key.lower(): val for key, val in CALLS[0]['headers'].items()}
        self.assertEqual(headers['x-api-key'], KEY)
        self.assertEqual(headers['anthropic-version'], '2023-06-01')
        self.assertNotIn('authorization', headers)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(CALLS[1]['path']).query)
        self.assertEqual(query, {'limit': ['1000'], 'after_id': ['claude-fixture-a']})

    def test_gemini_auth_page_token_and_supported_methods(self):
        value = self.discover('/gemini/v1beta', 'gemini')
        self.assertEqual(len(value['models']), 4)
        headers = {key.lower(): val for key, val in CALLS[0]['headers'].items()}
        self.assertEqual(headers['x-goog-api-key'], KEY)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(CALLS[1]['path']).query)
        self.assertEqual(query, {'pageSize': ['1000'], 'pageToken': ['next/&?']})
        self.assertEqual(value['models'][1]['supported_kinds'], ['image', 'chat'])
        self.assertEqual(value['models'][2]['supported_kinds'], [])
        self.assertEqual(value['models'][3]['supported_kinds'], [])
        self.assertNotIn('key=', CALLS[0]['path'])

    def test_generic_cursor_and_duplicate_loop_guard(self):
        self.assertEqual(self.discover('/cursor')['pages'], 2)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(CALLS[-1]['path']).query)
        self.assertEqual(query, {'cursor': ['cursor/&?']})
        CALLS.clear()
        error = self.discover('/loop', status=502)
        self.assertIn('重复', error['error'])
        self.assertEqual(len(CALLS), 2)

    def test_saved_key_reused_only_for_same_canonical_destination(self):
        saved = self.save()
        value = self.discover('/single/', id=saved['id'], api_key='')
        self.assertEqual(len(value['models']), 1)
        self.assertEqual(CALLS[-1]['headers']['Authorization'], 'Bearer ' + KEY)
        before = len(CALLS)
        error = self.discover('/openai', id=saved['id'], api_key='', status=400)
        self.assertIn('重新填写', error['error'])
        self.assertEqual(len(CALLS), before)
        self.assertEqual(providers.canonical_base_url('https://EXAMPLE.test:443/v1/'), 'https://example.test/v1')

    def test_save_different_base_clears_old_secret_and_same_base_retains(self):
        saved = self.save()
        updated = self.save('/single/', id=saved['id'], api_key='', name='Same destination')
        self.assertTrue(updated['has_key'])
        changed = self.save('/openai', id=saved['id'], api_key='', name='New destination')
        self.assertFalse(changed['has_key'])
        self.assertFalse(storage.get('providers', saved['id'])['secret'])

    def test_id_only_discovery_preserves_customized_saved_preset_destination(self):
        saved = self.save(platform='openai', protocol='openai_responses')
        value = self.api('/api/models/discover', {'id': saved['id']})
        self.assertEqual(value['base_url'], self.upstream + '/single')
        self.assertEqual(value['protocol'], 'openai_responses')
        self.assertEqual(CALLS[-1]['headers']['Authorization'], 'Bearer ' + KEY)

    def test_saved_list_path_validated_also_for_native_generation_protocol(self):
        self.api('/api/providers/save', {**self.config(), 'name': 'Invalid list path', 'model': 'gpt-fixture',
                                        'custom': {'discovery_path': 'https://evil.invalid/steal'}}, 400)
        self.assertFalse(storage.items('providers'))
        self.assertFalse(CALLS)

    def test_explicit_new_key_can_query_new_base_without_changing_saved_record(self):
        saved = self.save()
        self.discover('/openai', id=saved['id'], api_key='new-fixture-key')
        self.assertEqual(CALLS[-1]['headers']['Authorization'], 'Bearer new-fixture-key')
        old = storage.get('providers', saved['id'])
        self.assertEqual(old['base_url'], self.upstream + '/single')
        self.assertEqual(storage.crypt(old['secret'], decrypt=True), KEY)

    def test_custom_relative_get_path_items_and_auth_header(self):
        value = self.discover('/custom', 'custom', custom={'discovery_path': '/catalog',
                              'auth_header': 'X-Custom-Key', 'auth_prefix': ''})
        self.assertEqual(value['models'][0]['id'], 'gpt-custom-chat')
        self.assertEqual(value['models'][0]['protocol'], 'custom')
        headers = {key.lower(): val for key, val in CALLS[0]['headers'].items()}
        self.assertEqual(headers['x-custom-key'], KEY)
        self.assertEqual(CALLS[0]['path'], '/custom/catalog')

    def test_saved_native_generation_uses_custom_directory_without_changing_generation(self):
        custom = {'discovery_protocol': 'custom', 'discovery_path': '/custom-catalog',
                  'auth_header': 'X-Catalog-Key', 'auth_prefix': 'Catalog '}
        saved = self.save('/dual', custom=custom)
        self.assertEqual(saved['custom']['discovery_protocol'], 'custom')
        self.assertEqual(saved['protocol'], 'openai_chat')
        self.assertEqual(self.api('/api/providers/check', {'id': saved['id']}), {'models': ['gpt-dual-fixture']})
        discovered = self.api('/api/models/discover', {'id': saved['id']})
        self.assertEqual(discovered['models'][0]['protocol'], 'openai_chat')
        self.assertTrue(all(call['path'] == '/dual/custom-catalog' for call in CALLS))
        self.assertEqual(storage.get('providers', saved['id'])['protocol'], 'openai_chat')
        generation_headers = providers.headers(storage.get('providers', saved['id']))
        self.assertEqual(generation_headers['Authorization'], 'Bearer ' + KEY)
        self.assertNotIn('X-Catalog-Key', generation_headers)

    def test_saved_custom_generation_uses_native_directory_authentication(self):
        custom = {'discovery_protocol': 'openai_chat', 'submit_path': '/generate',
                  'body': {'model': '{{model}}', 'prompt': '{{prompt}}'}, 'text_path': 'reply',
                  'auth_header': 'X-Generation-Key', 'auth_prefix': 'Generate '}
        saved = self.save('/dual', protocol='custom', custom=custom)
        self.assertEqual(self.api('/api/providers/check', {'id': saved['id']}), {'models': ['gpt-dual-fixture']})
        discovered = self.api('/api/models/discover', {'id': saved['id']})
        self.assertEqual(discovered['models'][0]['protocol'], 'custom')
        self.assertTrue(all(call['path'] == '/dual/models' for call in CALLS))
        generation_headers = providers.headers(storage.get('providers', saved['id']))
        self.assertEqual(generation_headers['X-Generation-Key'], 'Generate ' + KEY)
        self.assertNotIn('Authorization', generation_headers)

    def test_explicit_discovery_protocol_overrides_saved_directory_protocol(self):
        saved = self.save('/dual', custom={'discovery_protocol': 'custom', 'discovery_path': '/custom-catalog',
                          'auth_header': 'X-Catalog-Key', 'auth_prefix': 'Catalog '})
        result = self.api('/api/models/discover', {'id': saved['id'], 'protocol': 'openai_chat',
                                                 'discovery_path': '/models'})
        self.assertEqual(result['models'][0]['id'], 'gpt-dual-fixture')
        self.assertEqual(CALLS[-1]['path'], '/dual/models')
        self.assertEqual(storage.get('providers', saved['id'])['custom']['discovery_protocol'], 'custom')

    def test_directory_protocol_and_custom_auth_validated_before_save_or_http(self):
        for custom in ({'discovery_protocol': 'openai_image'}, {'discovery_protocol': ['custom']},
                       {'discovery_protocol': 'custom', 'auth_header': 'Host'},
                       {'discovery_protocol': 'custom', 'auth_prefix': 'bad\nvalue'}):
            self.api('/api/providers/save', {**self.config(), 'name': 'Invalid directory',
                                            'model': 'gpt-fixture', 'custom': custom}, 400)
            self.discover(custom=custom, status=400)
        self.assertFalse(storage.items('providers'))
        self.assertFalse(CALLS)

    def test_invalid_path_header_and_local_optin_reject_before_http(self):
        for path in ('https://evil.invalid', '//evil.invalid', '/../models', '/models?key=secret'):
            self.discover('/custom', 'custom', custom={'discovery_path': path}, status=400)
        self.discover('/custom', 'custom', custom={'discovery_path': '/catalog', 'auth_header': 'Host'}, status=400)
        self.discover(allow_local=False, status=400)
        self.assertFalse(CALLS)

    def test_custom_missing_path_and_unsupported_presets_return_manual_fallback(self):
        value = self.discover('/custom', 'custom')
        self.assertFalse(value['supported'])
        self.assertEqual(value['models'], [])
        with patch.object(model_catalog.platform_catalog, 'get_preset', return_value={
            'id': 'fixture-unsupported', 'base_url': self.upstream + '/single',
            'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'unsupported', 'note': 'No list API'}):
            value = self.discover(platform='fixture-unsupported')
            self.assertFalse(value['supported'])
        self.assertFalse(CALLS)

    def test_empty_malformed_and_partial_lists_are_distinct(self):
        self.assertEqual(self.discover('/empty')['models'], [])
        for path in ('/missing', '/badshape', '/allbad'):
            self.discover(path, status=502)
        value = self.discover('/mixed')
        self.assertEqual(len(value['models']), 1)
        self.assertIn('2 条', value['caveat'])

    def test_model_count_page_and_response_limits(self):
        with patch.object(model_catalog, 'MAX_MODELS', 2):
            value = self.discover('/openai')
            self.assertEqual(len(value['models']), 2)
            self.assertTrue(value['truncated'])
        with patch.object(model_catalog, 'MAX_PAGES', 1):
            value = self.discover('/openai')
            self.assertEqual(value['pages'], 1)
            self.assertTrue(value['truncated'])
        with patch.object(model_catalog, 'MAX_RESPONSE', 128):
            self.discover('/large', status=502)

    def test_error_metadata_and_echoed_ids_do_not_leak_keys(self):
        error = self.discover('/error', status=502)
        self.assertIn('401', error['error'])
        value = self.discover('/echo')
        self.assertEqual(len(value['models']), 1)
        self.assertIn('隐藏', value['models'][0]['name'])

    def test_redirects_and_missing_list_endpoint_do_not_trigger_fallback_calls(self):
        self.discover('/redirect', status=502)
        self.assertEqual([call['path'] for call in CALLS], ['/redirect/models'])
        error = self.discover('/unsupported', status=502)
        self.assertIn('手动填写', error['error'])

    def test_model_discovery_csrf_origin_host_guards(self):
        body = self.config()
        self.api('/api/models/discover', body, 403, {'X-CSRF-Token': ''})
        self.api('/api/models/discover', body, 403, {'Origin': 'https://evil.invalid'})
        self.api('/api/models/discover', body, 403, {'Host': 'evil.invalid'})
        self.assertFalse(CALLS)

    def test_platform_catalog_and_existing_provider_check_contract(self):
        platforms = self.api('/api/platforms')['platforms']
        self.assertTrue(any(item['id'] == 'gemini' for item in platforms))
        self.assertTrue(any(item['id'] == 'custom' for item in platforms))
        saved = self.save()
        self.assertEqual(saved['platform'], 'custom')
        result = self.api('/api/providers/check', {'id': saved['id']})
        self.assertEqual(result, {'models': ['gpt-single']})


if __name__ == '__main__':
    unittest.main()
