"""HTTP integration acceptance for v2, using isolated data and loopback fixtures.

Run: python tests/verify_v2.py
No real provider, user data, or existing app process is accessed.
"""
import base64
import csv
import hashlib
import io
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image


APP = Path(__file__).resolve().parents[1]
WORK = APP / 'work'
RUN = WORK / ('acceptance-v2-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
KEY = 'fixture-only-not-a-real-api-key'
CONTEXT_MARKER = 'fixture user opted in: silver product photograph'
CALLS = []
LOCK = threading.Lock()
PASSES = []
FAILURES = []
JOBS = []
EXPECTED_TOKENS = {}
PROCESS = None
LOG = None
CSRF = ''
ORIGIN = ''
PROVIDER_URL = ''
FIXTURE = None


def picture(size=(128, 96), fmt='PNG', color=(70, 110, 170)):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, format=fmt)
    return out.getvalue()


PNG = picture()
JPEG = picture((64, 64), 'JPEG')
WEBP = picture((64, 64), 'WEBP')
FRAME = picture((1280, 720))
TAIL = picture((1280, 720), color=(180, 90, 80))
# A deterministic transport fixture for the adapter's MP4 header check. This is
# not a rendered model video and does not make visual-quality claims.
VIDEO = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom'
OPENAI_USAGE = {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120,
                'prompt_tokens_details': {'cached_tokens': 70},
                'completion_tokens_details': {'reasoning_tokens': 5}}


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, payload, code=200, mime='application/json'):
        raw = json.dumps(payload).encode('utf-8') if mime == 'application/json' else payload
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        with LOCK:
            CALLS.append({'method': 'GET', 'path': self.path, 'headers': dict(self.headers)})
        if self.path.endswith('/models'):
            return self.send({'data': [{'id': 'fixture-model'}]})
        if self.path.endswith('/content') or self.path == '/fixture.mp4':
            return self.send(VIDEO, mime='video/mp4')
        if self.path.startswith('/v1/tasks/'):
            return self.send({'task': {'id': 'custom-video', 'status': 'completed'},
                              'result': {'url': PROVIDER_URL.removesuffix('/v1') + '/fixture.mp4'},
                              'usage': {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15}})
        return self.send({'error': {'message': 'fixture route missing'}}, 404)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        content_type = self.headers.get('Content-Type', '')
        body = json.loads(raw) if content_type.startswith('application/json') else None
        parts = []
        if content_type.startswith('multipart/form-data'):
            message = BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + raw)
            parts = [{'name': item.get_param('name', header='content-disposition'),
                      'filename': item.get_filename(), 'mime': item.get_content_type(),
                      'raw': item.get_payload(decode=True)} for item in message.iter_parts()]
        request = {'method': 'POST', 'path': self.path, 'body': body,
                   'raw': raw, 'parts': parts, 'headers': dict(self.headers)}
        with LOCK:
            CALLS.append(request)
        if self.path.endswith('/images/edits') or self.path.endswith('/images/generations'):
            return self.send({'data': [{'b64_json': base64.b64encode(PNG).decode()}]})
        if self.path.endswith('/chat/completions'):
            text = json.dumps(body, ensure_ascii=False)
            if 'fixture-http-failure' in text:
                return self.send({'error': {'message': 'fixture failure ' + KEY},
                                  'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}, 429)
            if 'fixture-empty-answer' in text:
                return self.send({'choices': [{'message': {'content': ''}}],
                                  'usage': {'prompt_tokens': 4, 'completion_tokens': 2, 'total_tokens': 6}})
            return self.send({'id': 'chat-response-id', 'model': 'resolved-chat-model',
                              'choices': [{'message': {'content': 'fixture assistant answer'}}],
                              'usage': OPENAI_USAGE})
        if self.path.endswith('/responses'):
            return self.send({'id': 'responses-id', 'model': 'resolved-responses-model',
                              'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'responses answer'}]}],
                              'usage': {'input_tokens': 80, 'output_tokens': 30, 'total_tokens': 110,
                                        'input_tokens_details': {'cached_tokens': 20},
                                        'output_tokens_details': {'reasoning_tokens': 10}}})
        if self.path.endswith('/messages'):
            return self.send({'id': 'anthropic-id', 'model': 'resolved-anthropic-model',
                              'content': [{'type': 'text', 'text': 'anthropic answer'}],
                              'usage': {'input_tokens': 40, 'cache_creation_input_tokens': 10,
                                        'cache_read_input_tokens': 20, 'output_tokens': 15}})
        if self.path.endswith(':generateContent'):
            parts = [{'text': 'gemini answer'}]
            is_image = 'IMAGE' in body.get('generationConfig', {}).get('responseModalities', [])
            if is_image:
                parts.append({'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(PNG).decode()}})
            result = {'modelVersion': 'resolved-gemini-model', 'responseId': 'gemini-id',
                      'candidates': [{'content': {'parts': parts}}]}
            if not is_image:
                result['usageMetadata'] = {'promptTokenCount': 50, 'candidatesTokenCount': 12,
                                           'thoughtsTokenCount': 8, 'cachedContentTokenCount': 10,
                                           'totalTokenCount': 70}
            return self.send(result)
        if self.path.endswith('/videos'):
            return self.send({'id': 'native-video-id', 'status': 'completed'})
        if self.path == '/v1/custom/video':
            return self.send({'task': {'id': 'custom-video', 'status': 'queued'},
                              'usage': {'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12}})
        if self.path == '/v1/custom/chat':
            return self.send({'answer': 'custom answer', 'identity': {'model': 'resolved-custom', 'id': 'custom-id'},
                              'billing': {'input': 14, 'output': 6, 'cache': 4, 'reason': 2}})
        return self.send({'error': {'message': 'fixture route missing'}}, 404)


def fetch(path, body=None, expect=200, raw=False):
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': CSRF, 'Content-Type': 'application/json'}
    request = urllib.request.Request(ORIGIN + path,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as ex:
        status, data = ex.code, ex.read()
    assert status == expect, (path, status, data[:1000])
    return data if raw else json.loads(data)


def start():
    global PROCESS, CSRF, LOG
    LOG = (RUN / ('server-' + str(time.time_ns()) + '.log')).open('wb')
    environment = {**os.environ, 'GUANGYU_PORT': ORIGIN.rsplit(':', 1)[-1],
                   'GUANGYU_DATA': str(RUN / 'data'), 'PYTHONIOENCODING': 'utf-8'}
    PROCESS = subprocess.Popen([sys.executable, '-u', str(APP / 'server.py')], cwd=APP,
                               env=environment, stdout=LOG, stderr=LOG,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if PROCESS.poll() is not None:
            raise AssertionError('Isolated app exited during startup; see server log.')
        try:
            CSRF = fetch('/api/bootstrap')['csrf']
            return
        except (OSError, urllib.error.URLError):
            time.sleep(.05)
    raise AssertionError('Isolated app startup timed out.')


def stop():
    global PROCESS, LOG
    if PROCESS and PROCESS.poll() is None:
        try:
            fetch('/api/shutdown', {})
            PROCESS.wait(timeout=8)
        except Exception:
            PROCESS.terminate()
            try:
                PROCESS.wait(timeout=4)
            except subprocess.TimeoutExpired:
                PROCESS.kill()
                PROCESS.wait(timeout=4)
    PROCESS = None
    if LOG:
        LOG.close()
        LOG = None


def upload(raw, name='fixture.png'):
    return fetch('/api/uploads', {'name': name, 'data_base64': base64.b64encode(raw).decode()}, expect=201)


def save(kind, protocol, model='fixture-model', **fields):
    return fetch('/api/providers/save', {'name': 'fixture ' + protocol, 'kind': kind,
                 'protocol': protocol, 'model': model, 'base_url': PROVIDER_URL,
                 'allow_local': True, 'api_key': KEY, **fields})


def submit(provider, prompt='fixture prompt', **fields):
    return fetch('/api/jobs', {'provider_id': provider['id'], 'prompt': prompt, **fields}, expect=202)


def finish(value, expected_tokens=None, status='succeeded'):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = fetch('/api/jobs/' + value['id'])
        if value['status'] not in ('queued', 'submitting', 'polling') and value.get('finished_at') and value.get('archive_status') != 'pending':
            break
        time.sleep(.04)
    assert value['status'] == status, value
    assert value.get('finished_at') and value.get('started_at'), value
    assert isinstance(value['elapsed_ms'], (int, float)) and value['elapsed_ms'] >= 0
    assert value['usage']['total_tokens'] == expected_tokens, value['usage']
    JOBS.append(value)
    EXPECTED_TOKENS[value['id']] = expected_tokens
    return value


def latest(path):
    with LOCK:
        return next(value for value in reversed(CALLS) if value['method'] == 'POST' and value['path'].endswith(path))


def no_upstream(provider, **fields):
    with LOCK:
        before = len(CALLS)
    before_jobs = len(fetch('/api/jobs')['jobs'])
    fetch('/api/jobs', {'provider_id': provider['id'], 'prompt': 'invalid input fixture', **fields}, expect=400)
    with LOCK:
        assert len(CALLS) == before, 'Invalid input unexpectedly reached provider HTTP.'
    assert len(fetch('/api/jobs')['jobs']) == before_jobs, 'Invalid input was persisted as a submitted job.'


def check(name, callback):
    try:
        callback()
        PASSES.append(name)
        print('PASS ' + name, flush=True)
    except Exception as ex:
        FAILURES.append({'name': name, 'error': str(ex)[:2500], 'traceback': traceback.format_exc()})
        print('FAIL ' + name + ': ' + str(ex)[:350], flush=True)


def run():
    global FIXTURE, PROVIDER_URL, ORIGIN
    RUN.mkdir(parents=True)
    FIXTURE = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    FIXTURE.daemon_threads = True
    threading.Thread(target=FIXTURE.serve_forever, daemon=True).start()
    PROVIDER_URL = 'http://127.0.0.1:' + str(FIXTURE.server_port) + '/v1'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        ORIGIN = 'http://127.0.0.1:' + str(probe.getsockname()[1])
    start()
    assert fetch('/api/health')['version'] == (APP / 'VERSION').read_text(encoding='utf-8').strip()
    refs = [upload(PNG), upload(JPEG, 'fixture.jpg'), upload(WEBP, 'fixture.webp')]
    first, last = upload(FRAME, 'first.png'), upload(TAIL, 'last.png')

    def upload_validation():
        assert (refs[0]['width'], refs[0]['height'], refs[0]['mime']) == (128, 96, 'image/png')
        assert refs[1]['mime'] == 'image/jpeg' and refs[2]['mime'] == 'image/webp'
        assert fetch(refs[0]['url'], raw=True) == PNG
        assert fetch('/api/uploads/' + refs[0]['id']) == refs[0]
        for raw in (b'<script>not an image</script>', b'\x89PNG\r\n\x1a\nnot a real PNG', picture(fmt='GIF'), PNG[:-30]):
            fetch('/api/uploads', {'name': 'spoof.png', 'data_base64': base64.b64encode(raw).decode()}, expect=400)
        ihdr = struct.pack('>II', 10001, 10001) + PNG[24:29]
        oversized = PNG[:16] + ihdr + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr) & 0xffffffff) + PNG[33:]
        fetch('/api/uploads', {'name': 'dimensions.png', 'data_base64': base64.b64encode(oversized).decode()}, expect=400)
        fetch('/api/uploads', {'name': 'invalid.png', 'data_base64': '!not base64!'}, expect=400)
        spoof_name = upload(PNG, '../../spoof.jpg')
        assert spoof_name['mime'] == 'image/png' and spoof_name['url'].endswith('.png')
        assert '/' not in spoof_name['name'] and '\\' not in spoof_name['name']
    check('uploads verify dimensions/type/bytes and reject spoofed/truncated/oversized images', upload_validation)

    image = save('image', 'openai_image', 'gpt-image-1')
    def image_edits():
        value = finish(submit(image, input_assets={'references': [refs[0]['id'], refs[1]['id']]},
                              size='1024x1024', parameters={'quality': 'high', 'n': 2, 'background': 'transparent'}))
        request = latest('/images/edits')
        files = [part for part in request['parts'] if part['filename']]
        assert [(part['name'], part['mime'], part['raw']) for part in files] == [
            ('image[]', 'image/png', PNG), ('image[]', 'image/jpeg', JPEG)]
        fields = {part['name']: part['raw'].decode() for part in request['parts'] if not part['filename']}
        assert fields['n'] == '2' and fields['quality'] == 'high' and fields['background'] == 'transparent'
        assert fetch(value['result']['assets'][0]['url'], raw=True) == PNG
        assert 'data_base64' not in json.dumps(value) and base64.b64encode(PNG).decode() not in json.dumps(value)
    check('OpenAI image editing transmits actual multipart binary references and advanced parameters', image_edits)

    gemini_image = save('image', 'gemini', 'gemini-3-pro-image-preview')
    def gemini_reference():
        finish(submit(gemini_image, input_assets={'references': [refs[2]['id']]},
                      parameters={'aspect_ratio': '16:9', 'resolution': '2K'}))
        request = latest(':generateContent')['body']
        inline = request['contents'][-1]['parts'][-1]['inlineData']
        assert inline['mimeType'] == 'image/webp' and base64.b64decode(inline['data']) == WEBP
        assert request['generationConfig']['imageConfig'] == {'aspectRatio': '16:9', 'imageSize': '2K'}
    check('Gemini image references use inlineData and image configuration', gemini_reference)

    native_video = save('video', 'openai_video', 'sora-2')
    def video_first():
        value = finish(submit(native_video, input_assets={'first_frame': first['id']}, size='1280x720', seconds=4))
        files = [part for part in latest('/videos')['parts'] if part['filename']]
        assert len(files) == 1 and files[0]['name'] == 'input_reference' and files[0]['raw'] == FRAME
        assert fetch(value['result']['assets'][0]['url'], raw=True) == VIDEO
    check('Native video first frame is binary multipart and output downloads', video_first)

    def rejected_inputs():
        no_upstream(native_video, input_assets={'last_frame': last['id']}, size='1280x720')
        no_upstream(native_video, input_assets={'first_frame': refs[0]['id']}, size='1280x720')
        no_upstream(native_video, parameters={'seed': 42})
        no_upstream(image, parameters={'negative_prompt': 'unsupported'})
        no_upstream(image, input_assets={'references': ['0' * 32]})
        no_upstream(gemini_image, size='1024x1024')
        assert gemini_image['mapped_controls'] == {'size': False, 'seconds': False}
        assert native_video['mapped_controls'] == {'size': True, 'seconds': True}
    check('Unsupported tail/parameters, mismatched dimensions, missing uploads reject before HTTP', rejected_inputs)

    custom_config = {'submit_path': '/custom/video', 'poll_path': '/tasks/{id}',
                     'id_path': 'task.id', 'status_path': 'task.status', 'success_values': ['completed'],
                     'failure_values': ['failed'], 'media_path': 'result.url',
                     'capabilities': {'first_frame': True, 'last_frame': True, 'reference_images': True,
                                      'seed': True, 'negative_prompt': True, 'aspect_ratio': True,
                                      'camera': True, 'motion': True, 'strength': True, 'audio': True},
                     'body': {'model': '{{model}}', 'prompt': '{{prompt}}', 'first': '{{first_frame}}',
                              'last': '{{last_frame}}', 'refs': '{{reference_images}}', 'seed': '{{seed}}',
                              'negative': '{{negative_prompt}}', 'ratio': '{{aspect_ratio}}', 'camera': '{{camera}}',
                              'motion': '{{motion}}', 'strength': '{{strength}}', 'audio': '{{audio}}'}}
    custom_video = save('video', 'custom', custom=custom_config)
    def custom_frames():
        value = finish(submit(custom_video, input_assets={'first_frame': first['id'], 'last_frame': last['id'],
                             'references': [refs[0]['id']]}, parameters={'seed': 42, 'negative_prompt': 'blur',
                             'aspect_ratio': '16:9', 'camera': 'dolly', 'motion': 'slow', 'strength': .65, 'audio': True}), 15)
        body = latest('/custom/video')['body']
        assert base64.b64decode(body['first'].split(',', 1)[1]) == FRAME
        assert base64.b64decode(body['last'].split(',', 1)[1]) == TAIL
        assert base64.b64decode(body['refs'][0].split(',', 1)[1]) == PNG
        assert body['seed'] == 42 and type(body['seed']) is int
        assert body['strength'] == .65 and body['audio'] is True and body['camera'] == 'dolly'
        assert value['usage']['total_tokens'] == 15, 'Submit and poll snapshots must not be added.'
    check('Custom first/tail/reference data URI templates preserve parameters and merge polling usage', custom_frames)

    def custom_unmapped_controls():
        assert custom_video['mapped_controls'] == {'size': False, 'seconds': False}
        no_upstream(custom_video, size='1280x720')
        no_upstream(custom_video, seconds=8)
    check('Unmapped custom output size/duration reject before HTTP and mapped controls are explicit', custom_unmapped_controls)

    context = {'page': 'image', 'prompt': CONTEXT_MARKER, 'kind': 'image', 'model': 'gpt-image-1',
               'parameters': {'size': '1024x1024', 'quality': 'high'}}
    chat_connections = {}
    expectations = {'openai_chat': (100, 20, 70, 5), 'openai_responses': (80, 30, 20, 10),
                    'anthropic': (70, 15, 20, None), 'gemini': (50, 20, 10, 8), 'custom': (14, 6, 4, 2)}
    custom_chat = {'submit_path': '/custom/chat', 'text_path': 'answer',
                   'body': {'model': '{{model}}', 'messages': '{{messages}}'},
                   'usage_paths': {'input_tokens': 'billing.input', 'output_tokens': 'billing.output',
                                   'cached_input_tokens': 'billing.cache', 'reasoning_tokens': 'billing.reason'},
                   'response_model_path': 'identity.model', 'response_id_path': 'identity.id'}
    for protocol, expected in expectations.items():
        connection = save('chat', protocol, **({'custom': custom_chat} if protocol == 'custom' else {}))
        chat_connections[protocol] = connection
        def verify_chat(protocol=protocol, connection=connection, expected=expected):
            value = finish(submit(connection, assistant_context=context), expected[0] + expected[1])
            assert tuple(value['usage'][field] for field in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens')) == expected
            assert value.get('response_model') and value.get('response_id')
            path = {'openai_chat': '/chat/completions', 'openai_responses': '/responses', 'anthropic': '/messages',
                    'gemini': ':generateContent', 'custom': '/custom/chat'}[protocol]
            body = latest(path)['body']
            if protocol == 'openai_chat' or protocol == 'custom':
                assert body['messages'][0]['role'] == 'system' and '光屿 AI' in body['messages'][0]['content']
                assert any(CONTEXT_MARKER in item['content'] for item in body['messages'] if item['role'] == 'user')
            elif protocol == 'openai_responses':
                assert '光屿 AI' in body['instructions']
                assert all(item['role'] not in ('system', 'developer') for item in body['input'])
                assert CONTEXT_MARKER in json.dumps(body['input'])
            elif protocol == 'anthropic':
                assert '光屿 AI' in body['system'] and all(item['role'] != 'system' for item in body['messages'])
                assert CONTEXT_MARKER in json.dumps(body['messages'])
            elif protocol == 'gemini':
                assert '光屿 AI' in body['systemInstruction']['parts'][0]['text']
                assert all(item['role'] in ('user', 'model') for item in body['contents'])
                assert CONTEXT_MARKER in json.dumps(body['contents'])
            assert KEY not in json.dumps(value) and KEY not in json.dumps(body)
        check(protocol + ' assistant system/context and normalized reported usage', verify_chat)

    def custom_prompt_only():
        connection = save('chat', 'custom', custom={**custom_chat, 'body': {'prompt': '{{prompt}}'}})
        finish(submit(connection, assistant_context=context), 20)
        body = latest('/custom/chat')['body']
        assert 'system:' in body['prompt'] and '光屿 AI' in body['prompt'] and CONTEXT_MARKER in body['prompt']
    check('Prompt-only custom assistant retains system instruction and opted-in context', custom_prompt_only)

    def context_opt_in():
        connection = chat_connections['openai_chat']
        finish(submit(connection), 120)
        body = latest('/chat/completions')['body']
        assert CONTEXT_MARKER not in json.dumps(body) and len(body['messages']) == 2
        no_upstream(connection, assistant_context={'api_key': 'forbidden'})
        no_upstream(connection, assistant_context={'parameters': {'password': 'forbidden'}})
    check('Assistant context is opt-in and rejects private/unknown fields before HTTP', context_opt_in)

    def failed_usage():
        connection = chat_connections['openai_chat']
        with LOCK:
            before = len(CALLS)
        failed = finish(submit(connection, 'fixture-http-failure'), 3, 'failed')
        assert KEY not in failed['error']
        with LOCK:
            assert len(CALLS) == before + 1, 'Failed paid POST must never be automatically retried.'
        finish(submit(connection, 'fixture-empty-answer'), 6, 'failed')
    check('HTTP errors and empty answers preserve returned usage without automatic POST retry', failed_usage)

    def usage_api():
        value = fetch('/api/usage?period=all')
        summary = value['summary']
        expected = sum(count for count in EXPECTED_TOKENS.values() if count is not None)
        assert summary['requests'] == len(JOBS), (summary['requests'], len(JOBS))
        assert summary['total_tokens'] == expected, (summary['total_tokens'], expected)
        assert summary['usage_missing_requests'] == sum(count is None for count in EXPECTED_TOKENS.values())
        assert summary['failed'] == 2 and summary['connected_models'] >= 10
        assert all(row['total_tokens'] is None for row in value['requests'] if EXPECTED_TOKENS[row['id']] is None)
        encoded = json.dumps(value)
        assert KEY not in encoded and 'provider_snapshot' not in encoded and CONTEXT_MARKER not in encoded
        exported = fetch('/api/usage.csv?period=all', raw=True)
        assert exported.startswith(b'\xef\xbb\xbf')
        rows = list(csv.reader(io.StringIO(exported.decode('utf-8-sig'))))
        assert len(rows) == len(JOBS) + 1
        for row in rows[1:]:
            if EXPECTED_TOKENS[row[0]] is None:
                assert row[7:10] == ['', '', '']
        assert fetch('/api/usage?period=all&format=csv', raw=True) == exported
        fetch('/api/usage?period=invalid', expect=400)
    check('Usage HTTP/CSV aggregate reported totals, retain unknowns and expose connected models', usage_api)

    def history_identity():
        original = chat_connections['openai_chat']
        fetch('/api/providers/save', {**original, 'name': 'renamed fixture', 'model': 'new-model', 'api_key': ''})
        rows = fetch('/api/usage?period=all')['models']
        current = next(row for row in rows if row['provider_id'] == original['id'] and row['connected'])
        previous = next(row for row in rows if row['provider_id'] == original['id'] and row['historical'])
        assert current['requests'] == 0 and current['model'] == 'new-model'
        assert previous['requests'] >= 4 and previous['model'] == original['model']
    check('Connection/model edits retain historical attribution and zero-usage current row', history_identity)

    def persisted_after_restart():
        hashes = {item['id']: hashlib.sha256(fetch(item['url'], raw=True)).hexdigest() for item in (refs[0], first, last)}
        before = fetch('/api/usage?period=all')['summary']['total_tokens']
        stop()
        start()
        for item in (refs[0], first, last):
            assert fetch('/api/uploads/' + item['id']) == item
            assert hashlib.sha256(fetch(item['url'], raw=True)).hexdigest() == hashes[item['id']]
        assert fetch('/api/usage?period=all')['summary']['total_tokens'] == before
        first_job = next(value for value in JOBS if value.get('input_assets', {}).get('first_frame'))
        assert fetch('/api/jobs/' + first_job['id'])['input_assets'] == first_job['input_assets']
    check('Restart preserves uploaded metadata/bytes, job input IDs and usage totals', persisted_after_restart)


if __name__ == '__main__':
    try:
        run()
    except Exception as ex:
        FAILURES.append({'name': 'fixture setup/run', 'error': str(ex), 'traceback': traceback.format_exc()})
        print('FAIL fixture setup/run: ' + str(ex)[:500], flush=True)
    finally:
        stop()
        if FIXTURE:
            FIXTURE.shutdown()
            FIXTURE.server_close()
        RUN.mkdir(parents=True, exist_ok=True)
        report = {'passed': len(PASSES), 'failed': len(FAILURES), 'checks': PASSES, 'failures': FAILURES,
                  'jobs': len(JOBS), 'expected_reported_tokens': sum(value for value in EXPECTED_TOKENS.values() if value is not None),
                  'isolated_data': str(RUN / 'data'), 'scope': 'local mock HTTP integration; no paid APIs or live user data'}
        (RUN / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'passed': len(PASSES), 'failed': len(FAILURES), 'report': str(RUN / 'report.json')}, ensure_ascii=False), flush=True)
    sys.exit(1 if FAILURES else 0)
