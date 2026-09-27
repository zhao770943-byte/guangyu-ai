"""Isolated local fixture acceptance; never calls a real model provider."""
import base64, concurrent.futures, http.client, json, os, socket, subprocess, sys, threading, time, urllib.error, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT
RUN=ROOT/'work'/('acceptance-'+str(time.time_ns()))
RUN.mkdir(parents=True)
sys.path.insert(0,str(APP))
import storage, providers
KEY='fixture-secret-not-real-20260928'
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
# A generated 64x64 blue H.264 frame in a valid MP4 container. Keeping this tiny
# fixture inline makes the regression suite independent of an FFmpeg install.
VIDEO=base64.b64decode(
    'AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAMWbW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAAGQAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAkB0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAAGQAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAEAAAABAAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAABkAAAAAAABAAAAAAG4bWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAoAAAABABVxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABY21pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAASNzdGJsAAAAv3N0c2QAAAAAAAAAAQAAAK9hdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAEAAQABIAAAASAAAAAAAAAABFUxhdmM2Mi4yOC4xMDIgbGlieDI2NAAAAAAAAAAAAAAAGP//AAAANWF2Y0MBZAAK/+EAGGdkAAqs2UQmwEQAAAMABAAAAwBQPEiWWAEABmjr48siwP34+AAAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAADkwAAAAAAAAAAYc3R0cwAAAAAAAAABAAAAAQAABAAAAAAcc3RzYwAAAAAAAAABAAAAAQAAAAEAAAABAAAAFHN0c3oAAAAAAAAC3AAAAAEAAAAUc3RjbwAAAAAAAAABAAADRgAAAGJ1ZHRhAAAAWm1ldGEAAAAAAAAAIWhkbHIAAAAAAAAAAG1kaXJhcHBsAAAAAAAAAAAAAAAALWlsc3QAAAAlqXRvbwAAAB1kYXRhAAAAAQAAAABMYXZmNjIuMTIuMTAyAAAACGZyZWUAAALkbWRhdAAAAq4GBf//qtxF6b3m2Ui3lizYINkj7u94MjY0IC0gY29yZSAxNjUgcjMyMjMgMDQ4MGNiMCAtIEguMjY0L01QRUctNCBBVkMgY29kZWMgLSBDb3B5bGVmdCAyMDAzLTIwMjUgLSBodHRwOi8vd3d3LnZpZGVvbGFuLm9yZy94MjY0Lmh0bWwgLSBvcHRpb25zOiBjYWJhYz0xIHJlZj0zIGRlYmxvY2s9MTowOjAgYW5hbHlzZT0weDM6MHgxMTMgbWU9aGV4IHN1Ym1lPTcgcHN5PTEgcHN5X3JkPTEuMDA6MC4wMCBtaXhlZF9yZWY9MSBtZV9yYW5nZT0xNiBjaHJvbWFfbWU9MSB0cmVsbGlzPTEgOHg4ZGN0PTEgY3FtPTAgZGVhZHpvbmU9MjEsMTEgZmFzdF9wc2tpcD0xIGNocm9tYV9xcF9vZmZzZXQ9LTIgdGhyZWFkcz0yIGxvb2thaGVhZF90aHJlYWRzPTEgc2xpY2VkX3RocmVhZHM9MCBucj0wIGRlY2ltYXRlPTEgaW50ZXJsYWNlZD0wIGJsdXJheV9jb21wYXQ9MCBjb25zdHJhaW5lZF9pbnRyYT0wIGJmcmFtZXM9MyBiX3B5cmFtaWQ9MiBiX2FkYXB0PTEgYl9iaWFzPTAgZGlyZWN0PTEgd2VpZ2h0Yj0xIG9wZW5fZ29wPTAgd2VpZ2h0cD0yIGtleWludD0yNTAga2V5aW50X21pbj0xMCBzY2VuZWN1dD00MCBpbnRyYV9yZWZyZXNoPTAgcmNfbG9va2FoZWFkPTQwIHJjPWNyZiBtYnRyZWU9MSBjcmY9MjMuMCBxY29tcD0wLjYwIHFwbWluPTAgcXBtYXg9NjkgcXBzdGVwPTQgaXBfcmF0aW89MS40MCBhcT0xOjEuMDAAgAAAACZliIQAN//+4QP4FNdN/mOPQ9kBaFXLkbcSjp8gDW8Tm/+RMQM11w=='
)
CALLS=[];COUNTERS={};REDIRECT_HITS=[];TRANSIENT=[True]
class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,data,code=200,mime='application/json',headers=None):
        raw=json.dumps(data).encode() if mime=='application/json' else data
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/leak':REDIRECT_HITS.append(dict(self.headers));return self.send({})
        if self.path.endswith('/models'):return self.send({'data':[{'id':'fixture-model'}]})
        if self.path.endswith('/content'):return self.send(VIDEO,mime='video/mp4')
        if self.path=='/asset.mp4':return self.send(VIDEO,mime='video/mp4')
        if self.path.startswith('/v1/videos/'):
            if TRANSIENT[0]:TRANSIENT[0]=False;return self.send({'error':{'message':'temporary unavailable'}},503)
            return self.send({'id':'video-test','status':'completed','progress':100})
        if self.path.startswith('/v1/tasks/'):
            identity=self.path.split('/')[-1];COUNTERS[identity]=COUNTERS.get(identity,0)+1
            return self.send({'done':COUNTERS[identity]>1,'result':{'url':f'http://127.0.0.1:{self.server.server_port}/asset.mp4'}})
        return self.send({'error':{'message':'not found'}},404)
    def do_POST(self):
        raw=self.rfile.read(int(self.headers['Content-Length']));body=json.loads(raw) if 'application/json' in self.headers.get('Content-Type','') else None
        CALLS.append({'path':self.path,'body':body,'raw':raw,'headers':dict(self.headers)})
        if self.path=='/v1/error':return self.send({'error':{'message':'rejected '+KEY}},401)
        if self.path=='/v1/redirect':return self.send({},302,headers={'Location':f'http://127.0.0.1:{self.server.server_port}/leak'})
        if self.path.endswith('/images/generations'):return self.send({'data':[{'b64_json':base64.b64encode(PNG).decode()}]})
        if self.path.endswith('/chat/completions'):
            time.sleep(.4)
            return self.send({'choices':[{'message':{'content':'模拟答复（测试接口）：'+str(len(body['messages']))+' 条消息 <script>alert(1)</script>'}}]})
        if self.path.endswith('/responses'):return self.send({'output':[{'type':'message','content':[{'type':'output_text','text':'responses fixture'}]}]})
        if self.path.endswith('/messages'):return self.send({'content':[{'type':'text','text':'anthropic fixture'}]})
        if self.path.endswith(':generateContent'):
            parts=[{'text':'gemini fixture'}]
            if 'generationConfig' in body:parts.append({'inlineData':{'mimeType':'image/png','data':base64.b64encode(PNG).decode()}})
            return self.send({'candidates':[{'content':{'parts':parts}}]})
        if self.path.endswith('/videos'):return self.send({'id':'video-test','status':'queued'})
        if self.path=='/v1/custom':return self.send({'output':{'text':'custom fixture','base64':base64.b64encode(PNG).decode()}})
        if self.path=='/v1/async':return self.send({'task':{'id':'custom-video'}})
        return self.send({'error':{'message':'unknown endpoint'}},400)
fixture=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=fixture.serve_forever,daemon=True).start()
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
origin=f'http://127.0.0.1:{port}';provider_url=f'http://127.0.0.1:{fixture.server_port}/v1'
env={**os.environ,'GUANGYU_PORT':str(port),'GUANGYU_DATA':str(RUN/'data'),'PYTHONIOENCODING':'utf-8'}
log=(RUN/'server.log').open('w');process=None;csrf='';PASS=[]
def start():
    global process,csrf
    process=subprocess.Popen([sys.executable,'-u',str(APP/'server.py')],cwd=APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(60):
        try:csrf=call('/api/bootstrap')['csrf'];return
        except Exception:time.sleep(.1)
    raise AssertionError('server not ready')
def call(path,body=None,headers=None,expect=200):
    h={'Content-Type':'application/json','Origin':origin,'X-CSRF-Token':csrf};h.update(headers or {})
    req=urllib.request.Request(origin+path,data=None if body is None else json.dumps(body).encode(),headers=h)
    try:
        with urllib.request.urlopen(req,timeout=10) as r:code=r.status;raw=r.read()
    except urllib.error.HTTPError as e:code=e.code;raw=e.read()
    assert code==expect,(path,code,raw[:500])
    return json.loads(raw)
def good(name):PASS.append(name);print('PASS '+name,flush=True)
def save(kind,protocol,**kw):
    return call('/api/providers/save',{'name':'fixture '+protocol,'kind':kind,'protocol':protocol,'model':'fixture-model','base_url':provider_url,'allow_local':True,'api_key':KEY,**kw})
def create(p,prompt='fixture prompt',**kw):return call('/api/jobs',{'provider_id':p['id'],'prompt':prompt,**kw},expect=202)
def finish(j,status='succeeded'):
    for _ in range(150):
        j=call('/api/jobs/'+j['id'])
        if j['status'] not in ('queued','submitting','polling'):break
        time.sleep(.1)
    assert j['status']==status,j
    return j
try:
    start()
    assert call('/api/health')['ok'];good('health and bootstrap')
    key_enc=storage.crypt(KEY);assert key_enc!=KEY and storage.crypt(key_enc,True)==KEY;good('DPAPI round trip')
    p=save('image','openai_image');assert p['has_key'] and 'secret' not in p and 'api_key' not in p
    assert KEY not in json.dumps(call('/api/bootstrap'));assert KEY.encode() not in (RUN/'data'/'workspace.sqlite3').read_bytes();good('credential protection and API redaction')
    call('/api/providers/save',{**p,'api_key':'','name':'edited image'});assert call('/api/providers/check',{'id':p['id']})['models']==['fixture-model'];good('edit preserves key; read-only model check')
    j=finish(create(p));assert len(j['result']['assets'])==1
    media=j['result']['assets'][0]['url']
    with urllib.request.urlopen(origin+media) as response:assert response.read()==PNG
    good('image generation Base64 and local asset')
    chat=save('chat','openai_chat');j=finish(create(chat,'first question'));conv=j['conversation_id'];j2=finish(create(chat,'second question',conversation_id=conv))
    upstream_messages=[c for c in CALLS if c['path'].endswith('/chat/completions')][-1]['body']['messages']
    assert [m['role'] for m in upstream_messages]==['system','user','assistant','user']
    assert '光屿 AI 网页创作工作台的助手' in upstream_messages[0]['content']
    assert '无法读取 API 密钥' in upstream_messages[0]['content']
    assert upstream_messages[1]['content']=='first question' and upstream_messages[3]['content']=='second question'
    assert '4 条' in j2['result']['text'];assert len(call('/api/conversations')['conversations'][0]['messages'])==4;good('multi-turn chat persists four messages and sends assistant system instruction')
    j3=create(chat,'concurrency',conversation_id=conv);call('/api/jobs',{'provider_id':chat['id'],'prompt':'duplicate','conversation_id':conv},expect=400);finish(j3);good('same-conversation concurrency rejected')
    for protocol in ('openai_responses','anthropic','gemini'):
        pp=save('chat',protocol);finish(create(pp))
    pp=save('image','gemini');assert finish(create(pp))['result']['assets'];good('Responses Anthropic Gemini text and Gemini image adapters')
    video=save('video','openai_video');v=finish(create(video,size='1280x720',seconds=4));assert v['upstream_id']=='video-test'
    req=urllib.request.Request(origin+v['result']['assets'][0]['url'],headers={'Range':'bytes=0-11'})
    with urllib.request.urlopen(req) as r:assert r.status==206 and r.read()[4:8]==b'ftyp'
    assert any(c['body'] is None and b'name="seconds"' in c['raw'] for c in CALLS if c['path'].endswith('/videos'));good('multipart video submit polling MP4 download and range')
    assert sum(c['path'].endswith('/videos') for c in CALLS)==1 and not TRANSIENT[0];good('transient polling GET retried without repeating generation POST')
    custom={'submit_path':'/custom','auth_header':'X-Custom-Key','auth_prefix':'','body':{'model':'{{model}}','prompt':'{{prompt}}','messages':'{{messages}}','duration':'{{seconds}}'},'text_path':'output.text','base64_path':'output.base64'}
    cp=save('chat','custom',custom=custom);finish(create(cp));assert CALLS[-1]['headers']['X-Custom-Key']==KEY and isinstance(CALLS[-1]['body']['messages'],list)
    cp=save('image','custom',custom=custom);finish(create(cp));good('custom request template preserves JSON types; custom header and Base64')
    custom2={**custom,'submit_path':'/async','id_path':'task.id','poll_path':'/tasks/{id}','status_path':'done','success_values':['true'],'failure_values':['error'],'media_path':'result.url'}
    cp=save('video','custom',custom=custom2);cv=finish(create(cp));assert cv['result']['assets'][0]['type']=='video';good('custom asynchronous video with false/true status mapping')
    er=save('chat','custom',custom={**custom,'submit_path':'/error'});err=finish(create(er),status='failed');assert KEY not in json.dumps(err) and '401' in err['error'];good('upstream error reports status without credential leak')
    red=save('chat','custom',custom={**custom,'submit_path':'/redirect'});finish(create(red),status='failed');assert not REDIRECT_HITS;good('authenticated redirects blocked')
    body={'id':p['id']}
    call('/api/providers/delete',body,headers={'Origin':'https://evil.example'},expect=403)
    call('/api/providers/delete',body,headers={'X-CSRF-Token':''},expect=403)
    call('/api/providers/delete',body,headers={'Content-Type':'text/plain'},expect=415)
    call('/api/health',headers={'Host':'evil.example'},expect=403);good('Origin CSRF Content-Type and Host guards')
    bad={**p,'id':'','allow_local':False};call('/api/providers/save',bad,expect=400)
    for path in ('https://evil.example/x','//evil.example/x','/../x'):
        call('/api/providers/save',{**cp,'id':'','custom':{**custom2,'submit_path':path}},expect=400)
    call('/api/providers/save',{**cp,'id':'','custom':{**custom2,'body':{'prompt':'{{unknown}}'}}},expect=400);good('local HTTP opt-in endpoint and unknown-template validation')
    count_before=len(call('/api/jobs')['jobs']);calls_before=len(CALLS)
    process.terminate();process.wait(10);start()
    assert len(call('/api/jobs')['jobs'])==count_before and len(CALLS)==calls_before
    assert len(call('/api/conversations')['conversations'])>=4;good('restart preserves records with no repeated generation')
    # Persist two real jobs around process interruption; neither may be resubmitted.
    asyncp=save('video','custom',custom=custom2);COUNTERS['custom-video']=0
    pending=create(asyncp)
    for _ in range(60):
        pending=call('/api/jobs/'+pending['id'])
        if pending['status']=='polling':break
        time.sleep(.05)
    assert pending['upstream_id']=='custom-video'
    calls_before=len(CALLS);process.terminate();process.wait(10);start()
    finish(pending);assert len(CALLS)==calls_before;good('restart resumes saved task ID with no duplicate submission')
    # Safe resume must reject completed jobs.
    call('/api/jobs/resume',{'id':pending['id']},expect=400);good('resume endpoint refuses completed task')
    call('/api/providers/delete',{'id':p['id']});assert all(x['id']!=p['id'] for x in call('/api/bootstrap')['providers']);assert call('/api/jobs/'+j['id'])['id']==j['id'];good('provider deletion keeps historical results')
    # Retain isolated fixture and app for browser QA only when requested by runner.
    report={'passed':PASS,'count':len(PASS),'run_dir':str(RUN),'fixture_url':provider_url,'app_url':origin,'production_apis_called':False}
    (ROOT/'work'/'acceptance-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(PASS),'run_dir':str(RUN)},ensure_ascii=False),flush=True)
    if '--keep' in sys.argv:
        (ROOT/'work'/'qa-url.txt').write_text(origin,encoding='utf-8')
        while True:time.sleep(30)
finally:
    if process and process.poll() is None:process.terminate();process.wait(10)
    fixture.shutdown();fixture.server_close();log.close()
