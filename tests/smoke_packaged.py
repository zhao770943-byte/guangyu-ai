"""Exercise the real Windows bundle using only loopback fixtures and temp data.

Usage: python tests/smoke_packaged.py dist/GuangyuAI/GuangyuAI.exe [--report path]
The copied executable runs with no Python on PATH and from an unrelated CWD.
"""
import argparse
import base64
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
import wave
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

KEY = 'fixture-only-packaged-test-key'
EXPECTED_VERSION = (Path(__file__).resolve().parents[1] / 'VERSION').read_text(encoding='utf-8').strip()
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwCqgAAAGyAPsem+p5AAAAAElFTkSuQmCC')
ENTERED, RELEASE = threading.Event(), threading.Event()
AUTHENTICATED = []
UPSTREAM_CALLS = []
PASSES = []

def fixture_wav():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(b'\0\0'*1600)
    return stream.getvalue()


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, code=200):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        UPSTREAM_CALLS.append(('GET', self.path))
        if self.path=='/fixture.png':
            self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(PNG)));self.end_headers();self.wfile.write(PNG);return
        if self.path == '/v1/models':
            AUTHENTICATED.append(self.headers.get('Authorization') == 'Bearer ' + KEY)
            return self.send({'data': [{'id': 'local-fixture-model'}, {'id': 'gpt-image-1'}]})
        if self.path == '/fixture-health':
            return self.send({'fixture': True})
        return self.send({'error': 'fixture not found'}, 404)

    def do_POST(self):
        UPSTREAM_CALLS.append(('POST', self.path))
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path=='/v1/images/generations':return self.send({'data':[{'url':f'http://127.0.0.1:{self.server.server_port}/fixture.png'}]})
        if self.path == '/v1/audio/speech':
            raw=fixture_wav();self.send_response(200);self.send_header('Content-Type','audio/wav')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        if self.path != '/v1/chat/completions':
            return self.send({'error': 'fixture not found'}, 404)
        AUTHENTICATED.append(self.headers.get('Authorization') == 'Bearer ' + KEY)
        ENTERED.set()
        RELEASE.wait(25)
        return self.send({'id': 'fixture-answer', 'choices': [{'message': {'content': 'Portable fixture answer'}}],
                          'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}})


def check(value, label):
    if not value:
        raise AssertionError(label)
    PASSES.append(label)
    print('PASS:', label, flush=True)


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Packaged smoke test requires Windows.')
    original = args.executable.resolve()
    if not original.is_file():
        raise SystemExit('Executable does not exist: ' + str(original))
    if (original.parent / 'data').exists():
        raise SystemExit('Refusing to package-test a bundle containing runtime data.')
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    fixture.daemon_threads = True
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='guangyu-portable-') as temporary:
        root = Path(temporary)
        installation = root / '中文 空格目录' / '光屿 AI'
        shutil.copytree(original.parent, installation)
        executable = installation / original.name
        cwd = root / 'unrelated-working-directory'
        cwd.mkdir()
        port = free_port()
        origin = f'http://127.0.0.1:{port}'
        environment = os.environ.copy()
        environment.pop('GUANGYU_DATA', None)
        environment['GUANGYU_PORT'] = str(port)
        environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        environment['HTTP_PROXY'] = environment['HTTPS_PROXY'] = 'http://127.0.0.1:9'
        environment['NO_PROXY'] = ''
        csrf = ''

        def run(*arguments, expected=0, env=None):
            result = subprocess.run([str(executable), *arguments, '--no-browser'], cwd=cwd,
                                    env=env or environment, capture_output=True, timeout=45)
            if result.returncode != expected:
                log = installation / 'data' / 'service.log'
                tail = log.read_text(encoding='utf-8')[-6000:] if log.exists() else 'No log created.'
                console = (result.stdout + result.stderr).decode('utf-8', errors='replace')[-6000:]
                raise AssertionError(f'Executable returned {result.returncode}; expected {expected}. Log: {tail}\nCaptured: {console}')
            return result

        def request(path, body=None):
            headers = {}
            if body is not None:
                headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-CSRF-Token': csrf}
            req = urllib.request.Request(origin + path,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers=headers)
            with opener.open(req, timeout=5) as response:
                raw = response.read()
                return json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw

        try:
            run()
            health = request('/api/health')
            check(health['app'] == 'GuangyuAI' and health['version'] == EXPECTED_VERSION, 'Frozen executable starts without Python on PATH, from Chinese path and unrelated CWD')
            data = installation / 'data'
            check((data / 'workspace.sqlite3').is_file() and not (cwd / 'data').exists(), 'Default data directory stays beside executable')
            check(b'<html' in request('/') and len(request('/app.js')) > 1000 and len(request('/style.css')) > 1000, 'Bundled HTML, JS and CSS resources served')
            check(len(request('/connections.js')) > 1000 and len(request('/connections.css')) > 1000,
                  'Bundled connection management JavaScript and styles served')
            bootstrap = request('/api/bootstrap')
            csrf = bootstrap['csrf']
            check(bootstrap['providers'] == [] and bootstrap['jobs'] == [], 'Distribution starts with no providers, keys or history')
            platforms = request('/api/platforms')['platforms']
            by_platform = {item['id']: item for item in platforms}
            check({'openai', 'anthropic', 'gemini', 'deepseek', 'custom'} <= by_platform.keys()
                  and by_platform['openai']['protocols']['image'] == 'openai_image',
                  'Frozen bundle includes platform catalog with protocol presets')
            upstream_before = len(UPSTREAM_CALLS)
            discovery = request('/api/models/discover', {'platform': 'custom', 'kind': 'chat',
                                                       'protocol': 'openai_chat',
                                                       'base_url': f'http://127.0.0.1:{fixture.server_port}/v1',
                                                       'api_key': KEY, 'allow_local': True})
            discovered = {item['id']: item for item in discovery['models']}
            check({'local-fixture-model', 'gpt-image-1'} <= discovered.keys()
                  and discovery['source'] == 'api' and discovery['supported']
                  and discovered['gpt-image-1']['supported_kinds'] == ['image']
                  and discovered['gpt-image-1']['protocol'] == 'openai_image',
                  'Packaged discovery reads fixture models and matches image protocol')
            after_discovery = request('/api/bootstrap')
            check(UPSTREAM_CALLS[upstream_before:] == [('GET', '/v1/models')]
                  and AUTHENTICATED == [True] and not ENTERED.is_set()
                  and after_discovery['providers'] == [] and after_discovery['jobs'] == []
                  and after_discovery['conversations'] == [],
                  'Discovery uses one authenticated GET without saving providers or creating jobs')
            with closing(sqlite3.connect(data / 'workspace.sqlite3')) as database:
                empty_providers = database.execute('SELECT count(*) FROM providers').fetchone()[0] == 0
            check(empty_providers and KEY not in json.dumps(discovery)
                  and KEY not in json.dumps(after_discovery)
                  and KEY not in (data / 'service.log').read_text(encoding='utf-8'),
                  'Temporary discovery key is neither saved nor exposed in responses or log')
            upload = request('/api/uploads', {'name': 'fixture.png', 'data_base64': base64.b64encode(PNG).decode()})
            check(upload['width'] == 1 and upload['height'] == 1 and request(upload['url']) == PNG, 'Bundled Pillow validates and serves real uploaded PNG')
            provider = request('/api/providers/save', {'name': 'Packaged local fixture', 'kind': 'chat',
                                                     'protocol': 'openai_chat', 'model': 'local-fixture-model',
                                                     'base_url': f'http://127.0.0.1:{fixture.server_port}/v1',
                                                     'allow_local': True, 'api_key': KEY})
            check(provider['has_key'] and 'secret' not in provider and KEY not in json.dumps(request('/api/bootstrap')), 'Fixture API key is redacted from public responses')
            with closing(sqlite3.connect(data / 'workspace.sqlite3')) as database:
                stored = json.loads(database.execute('SELECT payload FROM providers').fetchone()[0])
            check(stored['secret'] and KEY not in json.dumps(stored), 'Windows DPAPI stores encrypted fixture key')
            request('/api/providers/check', {'id': provider['id']})
            check(AUTHENTICATED == [True, True], 'Stored DPAPI key decrypts correctly for loopback fixture request')
            run()
            check(request('/api/bootstrap')['csrf'] == csrf, 'Repeated launch reuses the same running server')
            alternate = environment.copy()
            alternate['GUANGYU_DATA'] = str(root / 'other-data')
            run(env=alternate, expected=1)
            check(request('/api/bootstrap')['csrf'] == csrf, 'Different data directory cannot silently reuse or stop this instance')
            job = request('/api/jobs', {'provider_id': provider['id'], 'prompt': 'fixture-only portable test'})
            check(ENTERED.wait(8), 'Packaged backend executes loopback fixture job')
            run('--stop', expected=1)
            check(request('/api/health')['ok'], 'Stop refuses while a generation job is active')
            RELEASE.set()
            for _ in range(100):
                result = request('/api/jobs/' + job['id'])
                if result['status'] == 'succeeded':
                    break
                if result['status'] in ('failed', 'interrupted'):
                    raise AssertionError(result['error'])
                time.sleep(.1)
            check(result['status'] == 'succeeded' and result['usage']['total_tokens'] == 10, 'Packaged chat completes with real response usage accounting')
            run('--stop')
            run()
            csrf = request('/api/bootstrap')['csrf']
            request('/api/providers/check', {'id': provider['id']})
            check(AUTHENTICATED == [True, True, True, True] and request('/api/jobs/' + job['id'])['status'] == 'succeeded', 'Provider, encrypted key and completed history persist across restart')
            audio_provider=request('/api/providers/save',{'name':'Packaged audio fixture','kind':'audio','protocol':'openai_speech',
                'model':'tts-1','base_url':f'http://127.0.0.1:{fixture.server_port}/v1','allow_local':True})
            audio_job=request('/api/jobs',{'provider_id':audio_provider['id'],'prompt':'Fixture audio playback'})
            for _ in range(100):
                audio_job=request('/api/jobs/'+audio_job['id'])
                if audio_job['status'] in ('succeeded','failed','interrupted'):break
                time.sleep(.1)
            audio_asset=audio_job.get('result',{}).get('assets',[{}])[0]
            check(audio_job['status']=='succeeded' and audio_asset.get('type')=='audio'
                  and request(audio_asset['url'])==fixture_wav() and len(request('/audio.js'))>1000,
                  'Packaged speech adapter saves playable WAV and serves audio workspace')
            report=request('/api/usage?period=all')
            check(report['summary']['audio_count']==1 and audio_job['usage']['total_tokens'] is None
                  and UPSTREAM_CALLS.count(('POST','/v1/audio/speech'))==1,
                  'Packaged audio counts outputs, preserves unknown tokens and submits once')
            image_provider=request('/api/providers/save',{'name':'Packaged remote image','kind':'image','protocol':'openai_image','model':'gpt-image-1','base_url':f'http://127.0.0.1:{fixture.server_port}/v1','allow_local':True})
            image_job=request('/api/jobs',{'provider_id':image_provider['id'],'prompt':'Fixture saved image'})
            for _ in range(100):
                image_job=request('/api/jobs/'+image_job['id'])
                if image_job.get('archive_status')=='saved':break
                time.sleep(.1)
            asset=image_job.get('result',{}).get('assets',[{}])[0]
            check(image_job.get('archive_status')=='saved' and asset.get('local') and request(asset['url'])==PNG,
                  'Packaged remote media is archived as an original local file')
            run('--stop');run();csrf=request('/api/bootstrap')['csrf']
            check(request('/api/jobs/'+image_job['id'])['archive_status']=='saved' and request(asset['url'])==PNG
                  and UPSTREAM_CALLS.count(('POST','/v1/images/generations'))==1,
                  'Packaged works library survives restart without another generation')
            run('--stop')
            alternate['GUANGYU_PORT'] = str(port)
            run(env=alternate)
            check((root / 'other-data' / 'workspace.sqlite3').is_file() and request('/api/bootstrap')['providers'] == [], 'GUANGYU_DATA override creates separate isolated data')
            run('--stop', env=alternate)
            collision = environment.copy()
            collision['GUANGYU_PORT'] = str(fixture.server_port)
            run(env=collision, expected=1)
            run('--stop', env=collision)
            with opener.open(f'http://127.0.0.1:{fixture.server_port}/fixture-health', timeout=3) as response:
                check(json.load(response)['fixture'], 'Port collision refuses startup and never stops unrelated service')
        finally:
            RELEASE.set()
            for target in (environment, locals().get('alternate')):
                if target:
                    try:
                        run('--stop', env=target)
                    except Exception:
                        pass
            fixture.shutdown()
            fixture.server_close()
            time.sleep(.5)
    report = {'ok': True, 'checks': len(PASSES), 'passed': PASSES,
              'scope': 'Packaged Windows executable and isolated loopback fixtures; no paid model calls'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
