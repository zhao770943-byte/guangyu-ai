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
        if parsed.path in ('/html404/models','/html200/models'):
            raw = ('<html>Not Found ' + KEY + '</html>').encode()
            self.send_response(404 if parsed.path=='/html404/models' else 200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == '/arrayerror/models':
            return self.send(['upstream unavailable'], 502)
        if parsed.path == '/redirect/models':
            return self.send({}, 302, {'Location': f'http://127.0.0.1:{self.server.server_port}/redirect-target'})
        if parsed.path == '/custom/catalog':
            return self.send({'items': [{'id': 'gpt-custom-chat', 'name': 'Custom model'}]})
        if parsed.path == '/custom-default/models':
            if self.headers.get('X-Custom-Key') != KEY or self.headers.get('Authorization'):
                return self.send({'error': {'message': 'wrong custom directory authentication'}}, 401)
            return self.send({'models': [{'id': 'gpt-custom-default'}]})
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
        if parsed.path == '/minimax/models':
            return self.send({'data': [{'id': 'MiniMax-M3'}, {'id': 'MiniMax-M2.5'},
                                      {'id': 'image-01'}, {'id': 'vendor-private-model'}]})
        return self.send({'error': {'message': 'not found'}}, 404)

    def do_POST(self):
        CALLS.append({'method': 'POST', 'path': self.path})
        self.send({'error': 'generation is forbidden in this fixture'}, 405)


class DiscoveryTests(unittest.TestCase):
    def test_success_status_html_reports_requested_path_without_echoed_secret(self):
        error=self.discover('/html200',status=502)['error']
        self.assertIn('HTTP 200',error)
        self.assertIn('GET /html200/models',error)
        self.assertIn('HTML',error)
        self.assertIn('/v1/models',error)
        self.assertNotIn(KEY,error)

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

    def test_known_model_constraints_do_not_follow_selected_purpose(self):
        for kind, protocol in (('image', 'openai_image'), ('video', 'openai_video'), ('chat', 'openai_chat')):
            entries = {item['id']: item for item in self.discover('/minimax', protocol, kind=kind, platform='minimax')['models']}
            self.assertEqual(entries['MiniMax-M3']['supported_kinds'], ['chat'])
            self.assertEqual(entries['MiniMax-M3']['protocol'], 'openai_chat')
            self.assertEqual(entries['MiniMax-M3']['model_constraints']['kinds'], ['chat'])
            self.assertEqual(entries['image-01']['model_constraints']['kinds'], ['image'])
            self.assertEqual(entries['vendor-private-model']['model_constraints']['kinds'], [])
        self.assertTrue(all(call['method'] == 'GET' for call in CALLS))
        for identity, kinds in (('gpt-image-1', ['image']), ('sora-2', ['video']), ('gpt-4o', ['chat']),
                                ('gemini-3-pro-image-preview', ['image', 'chat'])):
            self.assertEqual(providers.model_constraints(identity)['kinds'], kinds)
        for identity in ('minimax-image-next', 'qwen-image', 'gpt-private-renderer', 'gemini-fixture'):
            self.assertEqual(providers.model_constraints(identity)['kinds'], [])

    def test_save_rejects_known_model_wrong_output_kind_including_custom(self):
        for identity, kind, protocol in (('MiniMax-M3', 'image', 'openai_image'),
                                          ('MiniMax-M3', 'video', 'openai_video'),
                                          ('gpt-image-1', 'chat', 'openai_chat'),
                                          ('sora-2', 'image', 'openai_image'),
                                          ('MiniMax-M3', 'image', 'custom')):
            custom = {'submit_path': '/generate', 'body': {'model': '{{model}}', 'prompt': '{{prompt}}'},
                      'media_path': 'data.url'}
            error = self.api('/api/providers/save', {**self.config('/minimax', protocol), 'name': 'Wrong model purpose',
                            'model': identity, 'kind': kind, 'custom': custom,
                            'model_constraints': {'kinds': [kind]}}, 400)
            self.assertIn(identity, error['error'])
            self.assertIn('修正用途', error['error'])
        self.assertFalse(storage.items('providers'))
        self.assertFalse(CALLS)

    def test_legacy_wrong_connection_is_visible_but_blocked_before_job_or_http(self):
        saved = self.save('/minimax', platform='minimax', model='MiniMax-M3')
        legacy = storage.get('providers', saved['id'])
        legacy.update(kind='image', protocol='openai_image')
        storage.put('providers', legacy)
        public = self.api('/api/bootstrap')['providers'][0]
        self.assertEqual(public['kind'], 'image')
        self.assertEqual(public['model_constraints']['kinds'], ['chat'])
        with patch.object(server, 'dispatch') as dispatch:
            error = self.api('/api/jobs', {'provider_id': saved['id'], 'prompt': 'Do not submit this request'}, 400)
            dispatch.assert_not_called()
        self.assertIn('MiniMax-M3', error['error'])
        self.assertFalse(storage.items('jobs'))
        self.assertFalse(storage.items('conversations'))
        self.assertFalse(CALLS)
        fixed = self.save('/minimax', id=saved['id'], platform='minimax', model='MiniMax-M3', api_key='')
        self.assertEqual(fixed['kind'], 'chat')
        self.assertEqual(fixed['model_constraints']['kinds'], ['chat'])

    def test_unknown_models_preserve_custom_media_adapter_space(self):
        custom = {'submit_path': '/generate', 'body': {'model': '{{model}}', 'prompt': '{{prompt}}'},
                  'media_path': 'data.url'}
        for kind in ('image', 'video'):
            saved = self.save(protocol='custom', kind=kind, model='private-output-workflow', custom=custom)
            self.assertEqual(saved['model_constraints']['kinds'], [])
            provider = storage.get('providers', saved['id'])
            path, body, _ = providers.build(provider, {'prompt': 'fixture prompt', 'size': 'auto', 'seconds': 4})
            self.assertEqual(path, '/generate')
            self.assertEqual(body['model'], 'private-output-workflow')
        self.assertFalse(CALLS)

    def test_official_minimax_image_requires_native_or_custom_adapter_but_proxy_is_allowed(self):
        for hostname in ('api.minimax.cn', 'api.minimax.io'):
            error = self.api('/api/providers/save', {**self.config(protocol='openai_image'),
                             'name': 'Wrong MiniMax adapter', 'kind': 'image', 'model': 'image-01',
                             'base_url': 'https://' + hostname + '/v1'}, 400)
            self.assertIn('/image_generation', error['error'])
            self.assertIn('MiniMax 图像协议', error['error'])
        proxy = self.save(protocol='openai_image', kind='image', model='image-01',
                          base_url='https://minimax.proxy.example/v1')
        self.assertEqual(proxy['protocol'], 'openai_image')
        custom = {'submit_path': '/image_generation', 'body': {'model': '{{model}}', 'prompt': '{{prompt}}'},
                  'media_path': 'data.image_urls'}
        native = self.save(protocol='custom', kind='image', model='image-01', custom=custom,
                           base_url='https://api.minimax.cn/v1')
        self.assertEqual(native['protocol'], 'custom')
        self.assertFalse(CALLS)

    def test_request_errors_include_relative_path_without_query_or_secret(self):
        for prefix, status in (('/html404', 404), ('/arrayerror', 502)):
            saved = self.save(prefix)
            provider = storage.get('providers', saved['id'])
            with self.assertRaises(providers.ProviderError) as failure:
                providers.request(provider, '/models?diagnostic=private-query-value')
            message = str(failure.exception)
            self.assertIn('HTTP ' + str(status), message)
            self.assertIn('GET /models', message)
            self.assertNotIn('private-query-value', message)
            self.assertNotIn(KEY, message)
            self.assertNotIn(self.upstream, message)
            if status == 404:
                self.assertIn('模型用途', message)

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

    def test_every_preset_reads_the_actual_destination_even_with_legacy_support_metadata(self):
        for platform in ('dashscope', 'zhipu', 'minimax', 'ark'):
            value = self.discover('/single', platform=platform)
            self.assertTrue(value['supported'])
            self.assertEqual([item['id'] for item in value['models']], ['gpt-single'])
            self.assertEqual(CALLS[-1]['path'], '/single/models')
        with patch.object(model_catalog.platform_catalog, 'get_preset', return_value={
            'id': 'fixture-unsupported', 'base_url': self.upstream + '/single',
            'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'unsupported', 'note': 'No list API'}):
            value = self.discover(platform='fixture-unsupported')
            self.assertEqual([item['id'] for item in value['models']], ['gpt-single'])
        self.assertEqual(len(CALLS), 5)
        self.assertTrue(all(call['method'] == 'GET' and call['path'] == '/single/models' for call in CALLS))
        self.assertFalse(storage.items('providers'))
        self.assertFalse(storage.items('jobs'))

    def test_custom_directory_without_path_reads_default_models_path(self):
        value = self.discover('/custom-default', 'custom', custom={'auth_header': 'X-Custom-Key', 'auth_prefix': ''})
        self.assertEqual([item['id'] for item in value['models']], ['gpt-custom-default'])
        self.assertEqual(value['models'][0]['protocol'], 'custom')
        self.assertEqual(len(CALLS), 1)
        self.assertEqual(CALLS[0]['method'], 'GET')
        self.assertEqual(CALLS[0]['path'], '/custom-default/models')

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
        CALLS.clear()
        error = self.discover('/unsupported', 'custom', status=502)
        self.assertIn('HTTP 404', error['error'])
        self.assertNotIn('手动', error['error'])
        self.assertNotIn('models', error)
        self.assertEqual([call['path'] for call in CALLS], ['/unsupported/models'])
        self.assertTrue(all(call['method'] == 'GET' for call in CALLS))

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

    def test_platform_catalog_api_key_links_are_official_https_metadata(self):
        official_hosts = {
            'weijin':'www.weijinapi.top',
            'openai': 'platform.openai.com',
            'anthropic': 'platform.claude.com',
            'gemini': 'aistudio.google.com',
            'deepseek': 'platform.deepseek.com',
            'siliconflow': 'cloud.siliconflow.cn',
            'openrouter': 'openrouter.ai',
            'xai': 'console.x.ai',
            'ollama': 'ollama.com',
            'lmstudio': 'lmstudio.ai',
            'moonshot': 'platform.kimi.com',
            'dashscope': 'bailian.console.aliyun.com',
            'zhipu': 'bigmodel.cn',
            'minimax': 'platform.minimax.cn',
            'ark': 'console.volcengine.com',
        }
        catalog = {item['id']: item for item in self.api('/api/platforms')['platforms']}
        self.assertEqual(set(catalog), set(official_hosts) | {'custom'})
        for identity, hostname in official_hosts.items():
            with self.subTest(platform=identity):
                item = catalog[identity]
                link = urllib.parse.urlsplit(item['api_key_url'])
                self.assertEqual(link.scheme, 'https')
                self.assertEqual(link.hostname, hostname)
                self.assertIsNone(link.username)
                self.assertIsNone(link.password)
                self.assertIsNone(link.port)
                self.assertFalse(link.query)
                self.assertFalse(link.fragment)
                self.assertTrue(link.path.startswith('/'))
                self.assertEqual(item['api_key_label'],
                                 '下载本机服务' if identity in ('ollama', 'lmstudio') else '获取 API Key')
        self.assertFalse(catalog['custom'].get('api_key_url'))
        self.assertFalse(catalog['custom'].get('api_key_label'))
        self.assertFalse(CALLS)


if __name__ == '__main__':
    unittest.main()
