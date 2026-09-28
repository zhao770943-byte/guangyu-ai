"""HTTP adapters and declarative mappings. Generation POSTs are never retried."""
import base64, binascii, copy, json, re, socket, time
import urllib.error, urllib.parse, urllib.request
import storage, capabilities, uploads
PROTOCOLS = {'image':{'openai_image','minimax_image','gemini','custom'},'video':{'openai_video','custom'},'chat':{'openai_chat','openai_responses','anthropic','gemini','custom'},'audio':{'openai_speech','minimax_speech','custom'}}
MAX_JSON = 96*1024*1024
MAX_MEDIA = 512*1024*1024
POLL_SECONDS, POLL_TIMEOUT = 5, 1800
class ProviderError(Exception):
    def __init__(self, message, uncertain=False, retryable=False, response=None, code=None):
        super().__init__(message)
        self.uncertain = uncertain
        self.retryable = retryable
        self.response = response
        self.code = code
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def clean_error(text,p):
    key = storage.crypt(p.get('secret',''),decrypt=True)
    value = str(text)
    if key:
        for form in (key,urllib.parse.quote(key,safe=''),json.dumps(key)[1:-1]): value=value.replace(form,'[密钥已隐藏]')
    return re.sub(r'(?i)(bearer\s+)[^\s"<>]+',r'\1[已隐藏]',value)[:1200]
def validate_path(path,allow_id=False):
    if not isinstance(path,str) or not path.startswith('/') or path.startswith('//'): raise ValueError('接口路径必须以一个 / 开头，例如 /generations。')
    parts = urllib.parse.urlsplit(path)
    decoded = urllib.parse.unquote(path)
    if parts.scheme or parts.netloc or parts.fragment or '\\' in decoded or any(ord(x)<32 for x in decoded): raise ValueError('接口路径不能包含域名、反斜杠或控制字符。')
    if any(x in ('.','..') for x in decoded.split('/')): raise ValueError('接口路径不能使用 . 或 ..。')
    if ('{' in path or '}' in path) and not (allow_id and path.count('{id}')==1 and '{' not in path.replace('{id}','') and '}' not in path.replace('{id}','')): raise ValueError('轮询路径只支持一个 {id} 占位符。')
    return path
def endpoint(p,path):
    validate_path(path)
    return p['base_url'].rstrip('/')+path
def validate_base_url(value,allow_local=False):
    if not isinstance(value,str) or not value.strip() or len(value)>2000:raise ValueError('base_url 不能为空或过长。')
    value=value.strip();url=urllib.parse.urlsplit(value)
    if not url.hostname or url.username or url.password or url.query or url.fragment:raise ValueError('基础地址需为完整 URL，不包含密钥、用户名、查询参数或片段。')
    try:_=url.port
    except ValueError:raise ValueError('URL 端口无效。')
    if any(ord(c)<33 for c in value) or '\\' in value:raise ValueError('URL 含非法字符。')
    local=url.hostname.lower() in ('localhost','127.0.0.1','::1')
    if url.scheme!='https' and not(url.scheme=='http' and local and allow_local is True):raise ValueError('接口需使用 HTTPS；本机 HTTP 需勾选“允许本机 HTTP 服务”。')
    return value.rstrip('/')

def canonical_base_url(value):
    """Credential destination identity, ignoring only harmless URL spelling."""
    url=urllib.parse.urlsplit(value.strip().rstrip('/'))
    host=(url.hostname or '').lower()
    if ':' in host:host='['+host+']'
    port=url.port
    if port is not None and not(url.scheme.lower()=='https' and port==443 or url.scheme.lower()=='http' and port==80):host+=':'+str(port)
    return urllib.parse.urlunsplit((url.scheme.lower(),host,url.path.rstrip('/'),'',''))

def validate_discovery_path(value):
    if value in ('',None):return ''
    if not isinstance(value,str) or len(value)>500:raise ValueError('模型列表路径无效或过长。')
    validate_path(value)
    parsed=urllib.parse.urlsplit(value)
    if parsed.query or parsed.fragment:raise ValueError('模型列表路径只填写相对路径，不包含查询参数或片段。')
    return value

def validate_discovery_protocol(value):
    if value in ('',None):return ''
    if not isinstance(value,str) or value not in ('openai_chat','anthropic','gemini','custom'):
        raise ValueError('模型目录协议无效。')
    return value

def validate_custom_auth(custom):
    header=custom.get('auth_header','Authorization')
    prefix=custom.get('auth_prefix','Bearer ')
    if not isinstance(header,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,79}',header) or header.lower() in {'host','content-length','content-type','connection','cookie','origin','referer','proxy-authorization','transfer-encoding'}:
        raise ValueError('认证请求头无效或保留。')
    if not isinstance(prefix,str) or len(prefix)>100 or any(ord(ch)<32 for ch in prefix):
        raise ValueError('认证前缀无效或包含控制字符。')
    return header,prefix

def model_constraints(identity):
    """Known output kinds only; unknown IDs remain open to custom adapters.

    Vision inputs do not make a text model an image/video output model. Keep
    these rules narrower than catalog suggestions and independent of settings.
    """
    kinds=[]
    if isinstance(identity,str):
        model=identity.strip().lower().removeprefix('models/').rsplit('/',1)[-1]
        if audio_task(model):
            kinds=['audio']
        elif re.match(r'^(?:gpt-image-|chatgpt-image-|dall-e-)\d',model) or model in ('image-01','image-01-live'):
            kinds=['image']
        elif re.match(r'^sora-\d',model):
            kinds=['video']
        elif re.match(r'^gemini-\d[\w.-]*image(?:[.-]|$)',model):
            kinds=['image','chat']
        elif not any(part in model for part in ('image','video','imagine','flux','sdxl','stable-diffusion','cogvideo','embedding','embed-','rerank','whisper','audio','realtime','transcrib','tts','moderation')):
            if (re.match(r'^minimax-m\d+(?:[._-]|$)',model)
                    or re.match(r'^(?:gpt-(?:4o|[345])(?:[.-]|$)|chatgpt-(?:4o|latest)(?:[.-]|$)|o[1-9](?:[.-]|$))',model)
                    or re.match(r'^claude-(?:[234](?:[.-]|$)|(?:opus|sonnet|haiku)-\d)',model)
                    or re.match(r'^deepseek-(?:chat|reasoner|[vr]\d)(?:[._-]|$)',model)):
                kinds=['chat']
    reason={'chat':'该模型输出文本，图片或视频输入能力不代表可以生成图像或视频。',
            'image':'该模型用于生成图像。','video':'该模型用于生成视频。','audio':'该模型用于音频，请区分语音合成、识别与实时语音。'}.get(kinds[0],'') if len(kinds)==1 else ('该模型可用于图像生成和文本对话。' if kinds else '')
    return {'kinds':kinds,'reason':reason}

def audio_task(identity):
    model=str(identity or '').lower().rsplit('/',1)[-1]
    if re.match(r'^(?:tts-\d|gpt-4o-mini-tts(?:-|$)|speech-\d)',model) or re.search(r'(?:^|[-_])tts(?:[-_]|$)',model):return 'speech'
    if 'whisper' in model or 'transcrib' in model or re.search(r'(?:^|[-_])asr(?:[-_]|$)',model):return 'transcription'
    if 'realtime' in model:return 'realtime'
    if 'music' in model:return 'music'
    if 'audio' in model:return 'conversation'
    return ''

def validate_model_kind(provider):
    constraints=model_constraints(provider.get('model'))
    if constraints['kinds'] and provider.get('kind') not in constraints['kinds']:
        labels={'chat':'文本','image':'图像','video':'视频','audio':'音频'}
        expected=' / '.join(labels[kind] for kind in constraints['kinds'])
        actual=labels.get(provider.get('kind'),str(provider.get('kind')))
        raise ValueError(f"模型 {provider.get('model')} 支持的用途是 {expected}，不能用于{actual}。请编辑模型连接并修正用途。")
    if provider.get('kind')=='image' and provider.get('protocol')=='openai_image':
        hostname=urllib.parse.urlsplit(provider.get('base_url','')).hostname
        if hostname in ('api.minimax.cn','api.minimax.io'):
            raise ValueError('MiniMax 官方图像接口使用 /image_generation，不支持 OpenAI Images 的 /images/generations。请选择 MiniMax 图像协议。')
    if provider.get('protocol') in ('openai_speech','minimax_speech') and audio_task(provider.get('model')) not in ('','speech'):
        raise ValueError('该型号不是语音合成模型，不能使用文字转语音接口。请更换语音合成型号。')
    return constraints

def validate(p):
    if p.get('kind') not in PROTOCOLS or p.get('protocol') not in PROTOCOLS[p['kind']]: raise ValueError('用途与协议不匹配。')
    for field,maximum in [('name',60),('model',200),('base_url',2000)]:
        if not isinstance(p.get(field),str) or not p[field].strip() or len(p[field])>maximum: raise ValueError(f'{field} 不能为空或过长。')
        p[field]=p[field].strip()
    validate_model_kind(p)
    url=urllib.parse.urlsplit(p['base_url'])
    if not url.hostname or url.username or url.password or url.query or url.fragment: raise ValueError('基础地址需为完整 URL，不包含密钥、用户名、查询参数或片段。')
    try: _=url.port
    except ValueError: raise ValueError('URL 端口无效。')
    if any(ord(c)<33 for c in p['base_url']) or '\\' in p['base_url']: raise ValueError('URL 含非法字符。')
    local=url.hostname.lower() in ('localhost','127.0.0.1','::1')
    if url.scheme!='https' and not(url.scheme=='http' and local and p.get('allow_local') is True): raise ValueError('接口需使用 HTTPS；本机 HTTP 需勾选“允许本机 HTTP 服务”。')
    p['base_url']=p['base_url'].rstrip('/')
    if not isinstance(p.get('extra',{}),dict) or len(json.dumps(p.get('extra',{})))>24000: raise ValueError('附加参数必须是大小合理的 JSON 对象。')
    timeout = p.get('request_timeout_seconds')
    if timeout is not None and (type(timeout) is not int or not 60 <= timeout <= 1800):
        raise ValueError('响应等待上限应为 60–1800 秒的整数，留空使用按用途配置的默认值。')
    custom=p.get('custom') or {}
    if not isinstance(custom,dict):raise ValueError('自定义接口配置应为 JSON 对象。')
    validate_discovery_path(custom.get('discovery_path'))
    discovery_protocol=validate_discovery_protocol(custom.get('discovery_protocol'))
    if discovery_protocol=='custom':validate_custom_auth(custom)
    if p['protocol']=='custom':
        c=custom
        validate_path(c.get('submit_path',''))
        if c.get('poll_path'):
            validate_path(c['poll_path'],True)
            if '{id}' not in c['poll_path'] or not c.get('id_path') or not c.get('status_path'): raise ValueError('异步查询需填写任务 ID、状态路径和含 {id} 的轮询路径。')
            if not c.get('success_values'): raise ValueError('异步查询至少需要一个成功状态。')
        if not isinstance(c.get('body'),dict): raise ValueError('请求模板必须是 JSON 对象。')
        capabilities.validate_custom(c)
        substitute(c['body'],template_context(p,{'prompt':'prompt','messages':[],'size':'auto','seconds':4}))
        validate_custom_auth(c)
        if p['kind']=='chat' and not c.get('text_path'): raise ValueError('答疑接口需填写文本响应路径。')
        if p['kind']!='chat' and not(c.get('media_path') or (p['kind']=='image' and c.get('base64_path'))): raise ValueError('媒体接口需填写媒体 URL 或图片 Base64 响应路径。')
        for field in ('text_path','media_path','base64_path','id_path','status_path','response_model_path','response_id_path'):
            if c.get(field) and not re.fullmatch(r'[A-Za-z0-9_.-]{1,240}',c[field]): raise ValueError('字段路径只支持点号分隔的字段名和数字下标。')
        usage_paths=c.get('usage_paths',{})
        if not isinstance(usage_paths,dict) or any(k not in ('input_tokens','output_tokens','total_tokens','cached_input_tokens','reasoning_tokens') or not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,240}',v) for k,v in usage_paths.items()):raise ValueError('用量路径映射无效。')
        for field in ('success_values','failure_values'):
            if not isinstance(c.get(field,[]),list) or not all(isinstance(x,str) for x in c.get(field,[])): raise ValueError('状态映射应为字符串数组。')
    return p
def headers(p):
    key=storage.crypt(p.get('secret',''),decrypt=True)
    h={'Accept':'application/json','User-Agent':'GuangyuAI/2.0'}
    protocol=p['protocol']
    if protocol=='anthropic':
        h['anthropic-version']='2023-06-01'
        if key: h['x-api-key']=key
    elif protocol=='gemini':
        if key: h['x-goog-api-key']=key
    elif protocol=='custom':
        if key:
            c=p['custom'];h[c.get('auth_header','Authorization')]=c.get('auth_prefix','Bearer ')+key
    elif key: h['Authorization']='Bearer '+key
    return h
def request_timeout(p, submitting=True):
    # Submission may synchronously render a large image. Poll GETs stay bounded
    # independently; a lost POST response is never permission to submit again.
    if not submitting:return 150
    return p.get('request_timeout_seconds') or {'image':600,'video':300}.get(p.get('kind'),150)


def request(p,path,payload=None,multipart=False,binary=False):
    h=headers(p);data=None
    if payload is not None:
        if multipart:
            boundary='Guangyu'+storage.uid();parts=[]
            for k,v in payload.items():
                if not re.fullmatch(r'[A-Za-z0-9_-]+(?:\[\])?',k): raise ProviderError('表单参数名称无效。')
                files=v if isinstance(v,list) and v and all(isinstance(item,FilePart) for item in v) else [v]
                for value in files:
                    if isinstance(value,FilePart):
                        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{value.filename}"\r\nContent-Type: {value.mime}\r\n\r\n'.encode()+value.raw+b'\r\n')
                    else:
                        val=json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list,bool)) else str(value)
                        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{val}\r\n'.encode())
            data=b''.join(parts)+f'--{boundary}--\r\n'.encode();h['Content-Type']='multipart/form-data; boundary='+boundary
        else:
            data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode();h['Content-Type']='application/json'
    req=urllib.request.Request(endpoint(p,path),data=data,headers=h,method='POST' if data is not None else 'GET')
    timeout=request_timeout(p, submitting=payload is not None)
    try:
        with OPENER.open(req,timeout=timeout) as response: raw=response.read(MAX_JSON+1)
        if len(raw)>MAX_JSON: raise ProviderError('模型响应超过 96 MiB，已停止读取。')
        if binary:return raw
        try: result=json.loads(raw)
        except (ValueError,UnicodeDecodeError): raise ProviderError('接口未返回 JSON，请核对基础地址和协议。')
        if not isinstance(result,dict): raise ProviderError('接口响应必须为 JSON 对象。')
        if result.get('error'): raise ProviderError(clean_error(json.dumps(result['error'],ensure_ascii=False),p),response=result)
        return result
    except urllib.error.HTTPError as ex:
        if 300<=ex.code<400: raise ProviderError('接口返回重定向；为避免密钥外泄未跟随。请填写最终 API 地址。')
        raw=ex.read(8000).decode('utf-8',errors='replace')
        obj=None
        try:
            obj=json.loads(raw);error=obj.get('error',obj.get('message',obj)) if isinstance(obj,dict) else obj;detail=str(error.get('message',error) if isinstance(error,dict) else error)
        except ValueError: detail='接口返回非 JSON 错误，请检查平台服务。'
        safe_path=clean_error(urllib.parse.unquote(urllib.parse.urlsplit(path).path),p)
        guidance=' 请核对模型用途、接口协议和请求路径。' if ex.code in (404,405) else ''
        raise ProviderError(f'平台返回 HTTP {ex.code}（{req.get_method()} {safe_path}）：{clean_error(detail,p)}{guidance}',retryable=payload is None and ex.code in (408,429,500,502,503,504),response=obj if isinstance(obj,dict) else None) from None
    except (urllib.error.URLError,TimeoutError,socket.timeout,ConnectionError,OSError) as ex:
        timed_out=isinstance(ex,TimeoutError) or isinstance(getattr(ex,'reason',None),TimeoutError)
        message=f'等待平台响应超时（网络等待上限 {timeout} 秒）。' if timed_out else '与平台的网络连接中断，未收到完整响应。'
        message+=('平台可能仍在处理，是否完成或扣费尚未确认。请先核对平台任务与用量；本机不会自动重复提交。' if payload is not None
                  else '本次仅查询原任务，未重新生成；可稍后继续查询。')
        raise ProviderError(message,uncertain=payload is not None,retryable=payload is None,
                            code='response_timeout' if timed_out else 'connection_interrupted') from None
def dig(obj,path):
    if not path:return None
    for key in path.split('.'):
        if isinstance(obj,dict):obj=obj.get(key)
        elif isinstance(obj,list) and key.isdigit() and int(key)<len(obj):obj=obj[int(key)]
        else:return None
    return obj
def substitute(obj,context):
    if isinstance(obj,dict):return {k:substitute(v,context) for k,v in obj.items()}
    if isinstance(obj,list):return [substitute(v,context) for v in obj]
    if not isinstance(obj,str):return obj
    matches=re.findall(r'\{\{(.*?)\}\}',obj)
    for key in matches:
        if key not in context:raise ValueError('未知模板变量：'+key)
    if len(matches)==1 and obj=='{{'+matches[0]+'}}':return copy.deepcopy(context[matches[0]])
    for key in matches:
        value=context[key];obj=obj.replace('{{'+key+'}}',json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value))
    return obj
def merge(base,extra):
    output=copy.deepcopy(base)
    for k,v in extra.items():output[k]=merge(output[k],v) if isinstance(v,dict) and isinstance(output.get(k),dict) else copy.deepcopy(v)
    return output
class FilePart:
    def __init__(self,identity):
        record,self.raw=uploads.binary(identity)
        self.filename,self.mime=record['filename'],record['mime']

def template_context(p,job):
    inputs=job.get('input_assets') or {}
    context={'model':p.get('model',''),'prompt':job['prompt'],'messages':job.get('messages',[{'role':'user','content':job['prompt']}]),'size':job.get('size','auto'),'seconds':job.get('seconds',4),
             'first_frame':uploads.data_uri(inputs['first_frame']) if inputs.get('first_frame') else None,
             'last_frame':uploads.data_uri(inputs['last_frame']) if inputs.get('last_frame') else None,
             'reference_images':[uploads.data_uri(identity) for identity in inputs.get('references',[])]}
    context.update({key:None for key in capabilities.PARAMETERS})
    context.update(job.get('parameters') or {})
    context['system']='\n\n'.join(m['content'] for m in context['messages'] if m['role'] in ('system','developer'))
    return context

def build(p,job):
    validate_model_kind(p)
    import video_controls
    video_controls.validate(p,job.get('size','auto'),job.get('seconds',4))
    protocol,kind=p['protocol'],p['kind'];prompt,model=job['prompt'],p['model']
    messages=job.get('messages',[{'role':'user','content':prompt}]);multipart=False
    inputs,params,_=capabilities.validate_job(p,job.get('input_assets'),job.get('parameters'),job.get('size','auto'))
    conversation=[m for m in messages if m['role'] not in ('system','developer')]
    system='\n\n'.join(m['content'] for m in messages if m['role'] in ('system','developer'))
    if protocol=='custom':
        path=p['custom']['submit_path'];template=capabilities.request_template(p)
        used=capabilities.template_variables(template)
        required=set(params) | ({'reference_images'} if inputs['references'] else set()) | {k for k in ('first_frame','last_frame') if inputs[k]}
        if kind in ('image','video') and job.get('size','auto')!='auto':required.add('size')
        if kind=='video' and job.get('seconds',4)!=4:required.add('seconds')
        if required-used:raise ValueError('自定义请求模板的实际内容未引用已提交参数：'+', '.join(sorted(required-used)))
        context=template_context(p,job)
        # Prompt-only adapters still receive the assistant instruction and history.
        if kind=='chat' and 'messages' not in used:
            context['prompt']='\n\n'.join(m['role']+': '+m['content'] for m in messages)
        body=substitute(template,context)
    elif protocol=='openai_chat':path,body='/chat/completions',{'model':model,'messages':messages,'stream':False}
    elif protocol=='openai_responses':
        path,body='/responses',{'model':model,'input':conversation,'stream':False}
        if system:body['instructions']=system
    elif protocol=='anthropic':
        path,body='/messages',{'model':model,'messages':conversation,'max_tokens':p.get('extra',{}).get('max_tokens',4096)}
        if system:body['system']=system
    elif protocol=='gemini':
        path='/models/'+urllib.parse.quote(model.removeprefix('models/'),safe='')+':generateContent'
        body={'contents':[{'role':'model' if m['role']=='assistant' else 'user','parts':[{'text':m['content']}]} for m in conversation]}
        if system:body['systemInstruction']={'parts':[{'text':system}]}
        if kind=='image':
            body['generationConfig']={'responseModalities':['TEXT','IMAGE']}
            image_config={}
            if 'aspect_ratio' in params:image_config['aspectRatio']=params['aspect_ratio']
            if 'resolution' in params:image_config['imageSize']=params['resolution']
            if image_config:body['generationConfig']['imageConfig']=image_config
            for identity in inputs['references']:
                record,raw=uploads.binary(identity)
                body['contents'][-1]['parts'].append({'inlineData':{'mimeType':record['mime'],'data':base64.b64encode(raw).decode('ascii')}})
    elif protocol=='openai_image':
        path,body='/images/generations',{'model':model,'prompt':prompt}
        if job.get('size')!='auto':body['size']=job['size']
        body.update(params)
        if inputs['references']:
            path,multipart='/images/edits',True
            body['image' if model.lower()=='dall-e-2' else 'image[]']=[FilePart(identity) for identity in inputs['references']]
    elif protocol=='minimax_image':
        if len(prompt)>1500:raise ValueError('MiniMax 图像描述最多 1500 字符。')
        path,body='/image_generation',{'model':model,'prompt':prompt,'response_format':'url',**params}
    elif protocol in ('openai_speech','minimax_speech'):
        if len(prompt)>(4096 if protocol=='openai_speech' else 9999):raise ValueError('语音文本超过当前接口长度限制。')
        voice=params.get('voice') or p.get('extra',{}).get('voice') or ('alloy' if protocol=='openai_speech' else 'male-qn-qingse')
        speed=params.get('speed',1)
        if protocol=='openai_speech':path,body='/audio/speech',{'model':model,'input':prompt,'voice':voice,'speed':speed,'response_format':'wav'}
        else:path,body='/t2a_v2',{'model':model,'text':prompt,'stream':False,'output_format':'url','voice_setting':{'voice_id':voice,'speed':speed,'vol':1,'pitch':0},'audio_setting':{'format':'mp3','sample_rate':32000,'bitrate':128000,'channel':1}}
    elif protocol=='openai_video':
        path,body,multipart='/videos',{'model':model,'prompt':prompt,'seconds':str(job.get('seconds',4))},True
        if job.get('size')!='auto':body['size']=job['size']
        if inputs['first_frame']:body['input_reference']=FilePart(inputs['first_frame'])
    else:raise ProviderError('不支持的协议。')
    if protocol!='custom':
        # UI-selected inputs/model/conversation win over connection defaults.
        body=merge(p.get('extra',{}),body)
    if kind=='chat' and protocol not in ('custom','gemini'):body['stream']=False
    if protocol=='openai_responses':body['background']=False
    return path,body,multipart

def _count(value):
    return value if type(value) is int and value>=0 else None

def normalize_usage(p,response):
    """Usage snapshots are replaced/merged, never added during polling."""
    response=response if isinstance(response,dict) else {}
    protocol=p.get('protocol');raw=response.get('usage') or {};raw=raw if isinstance(raw,dict) else {}
    i=o=c=r=reported=None;source='unreported'
    if protocol=='gemini':
        raw=response.get('usageMetadata') or response.get('usage_metadata') or {}
        if isinstance(raw,dict):
            i=_count(raw.get('promptTokenCount'));candidate=_count(raw.get('candidatesTokenCount'));r=_count(raw.get('thoughtsTokenCount'))
            o=(candidate+(r or 0)) if candidate is not None else None
            c=_count(raw.get('cachedContentTokenCount'));reported=_count(raw.get('totalTokenCount'))
            if any(x is not None for x in (i,o,c,r,reported)):source='api:usageMetadata'
    elif protocol=='anthropic':
        base=_count(raw.get('input_tokens'));creation=_count(raw.get('cache_creation_input_tokens'));c=_count(raw.get('cache_read_input_tokens'))
        i=base+(creation or 0)+(c or 0) if base is not None else None
        o=_count(raw.get('output_tokens'));reported=_count(raw.get('total_tokens'))
        if any(x is not None for x in (i,o,c,reported)):source='api:usage'
    else:
        i=_count(raw.get('input_tokens',raw.get('prompt_tokens')));o=_count(raw.get('output_tokens',raw.get('completion_tokens')))
        reported=_count(raw.get('total_tokens'))
        c=_count(dig(raw,'input_tokens_details.cached_tokens'))
        if c is None:c=_count(dig(raw,'prompt_tokens_details.cached_tokens'))
        r=_count(dig(raw,'output_tokens_details.reasoning_tokens'))
        if r is None:r=_count(dig(raw,'completion_tokens_details.reasoning_tokens'))
        if any(x is not None for x in (i,o,c,r,reported)):source='api:usage'
    if protocol=='custom' and (p.get('custom') or {}).get('usage_paths'):
        paths=p['custom']['usage_paths'];mapped={k:_count(dig(response,v)) for k,v in paths.items()}
        i=mapped.get('input_tokens',i);o=mapped.get('output_tokens',o);c=mapped.get('cached_input_tokens',c);r=mapped.get('reasoning_tokens',r);reported=mapped.get('total_tokens',reported)
        if any(v is not None for v in mapped.values()):source='api:custom_mapping'
    total=i+o if i is not None and o is not None else reported
    return {'input_tokens':i,'output_tokens':o,'total_tokens':total,'cached_input_tokens':c,'reasoning_tokens':r,'reported_total_tokens':reported,'source':source}

def response_meta(p,response):
    c=p.get('custom') or {};response=response if isinstance(response,dict) else {}
    model=dig(response,c.get('response_model_path','')) if c.get('response_model_path') else response.get('model',response.get('modelVersion'))
    identity=dig(response,c.get('response_id_path','')) if c.get('response_id_path') else response.get('id',response.get('responseId'))
    return {'usage':normalize_usage(p,response),'response_model':model[:240] if isinstance(model,str) else None,'response_id':str(identity)[:300] if isinstance(identity,(str,int)) else None}

def record_response(p,job_id,response):
    metadata=response_meta(p,response)
    if not job_id:return metadata
    with storage.LOCK:
        job=storage.get('jobs',job_id)
        if not job:return metadata
        previous=job.get('usage') or {};current=metadata['usage']
        current={k:(previous.get(k) if value is None or (k=='source' and value=='unreported') else value) for k,value in current.items()}
        if current.get('source') is None:current['source']='unreported'
        if current.get('input_tokens') is not None and current.get('output_tokens') is not None:current['total_tokens']=current['input_tokens']+current['output_tokens']
        metadata['usage']=current
        for key in ('response_model','response_id'):
            if metadata[key] is None:metadata[key]=job.get(key)
        storage.update_job(job_id,**metadata)
    return metadata
def save_image(data,job_id):
    try:raw=base64.b64decode(data,validate=True)
    except (ValueError,binascii.Error,TypeError):raise ProviderError('图片 Base64 响应无效。')
    if len(raw)>MAX_JSON:raise ProviderError('图片超过大小限制。')
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):ext='png'
    elif raw.startswith(b'\xff\xd8\xff'):ext='jpg'
    elif raw[:6] in (b'GIF87a',b'GIF89a'):ext='gif'
    elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP':ext='webp'
    else:raise ProviderError('图片格式不受支持，仅支持 PNG、JPEG、GIF 和 WebP。')
    name=job_id+'-'+storage.uid()[:8]+'.'+ext;path=storage.DATA/'media'/name;temp=path.with_suffix('.partial')
    temp.write_bytes(raw);temp.replace(path)
    return {'type':'image','url':'/media/'+name,'local':True}
def media_url(value,kind):
    if not isinstance(value,str):raise ProviderError('媒体 URL 不是字符串。')
    url=urllib.parse.urlsplit(value)
    if url.scheme not in ('https','http') or not url.hostname or url.username or url.password or any(ord(x)<32 for x in value):raise ProviderError('响应中的媒体 URL 无效。')
    return {'type':kind,'url':value,'local':False}

def save_audio(raw,job_id):
    if len(raw)<44 or raw[:4]!=b'RIFF' or raw[8:12]!=b'WAVE':raise ProviderError('语音接口未返回 WAV 音频，请核对模型与协议。')
    name=job_id+'-'+storage.uid()[:8]+'.wav';path=storage.DATA/'media'/name;temp=path.with_suffix('.partial')
    try:temp.write_bytes(raw);temp.replace(path)
    finally:
        if temp.exists():temp.unlink()
    return {'type':'audio','url':'/media/'+name,'local':True}
def extract(p,result,job_id):
    protocol,kind=p['protocol'],p['kind'];text='';assets=[]
    if protocol=='custom':
        c=p['custom'];raw_text=dig(result,c.get('text_path',''))
        if isinstance(raw_text,str):text=raw_text
        if kind in ('image','video','audio'):
            url=dig(result,c.get('media_path',''))
            for item in url if isinstance(url,list) else ([url] if url else []):assets.append(media_url(item,kind))
            encoded=dig(result,c.get('base64_path',''))
            if encoded and kind=='image':
                for item in encoded if isinstance(encoded,list) else [encoded]:assets.append(save_image(item,job_id))
    elif protocol=='openai_chat':
        content=dig(result,'choices.0.message.content')
        if isinstance(content,str):text=content
        elif isinstance(content,list):text='\n'.join(x.get('text','') for x in content if isinstance(x,dict))
    elif protocol=='openai_responses':text='\n'.join(part.get('text','') for item in result.get('output',[]) if item.get('type')=='message' for part in item.get('content',[]) if part.get('type')=='output_text')
    elif protocol=='anthropic':text='\n'.join(part.get('text','') for part in result.get('content',[]) if part.get('type')=='text')
    elif protocol=='gemini':
        for candidate in result.get('candidates',[]):
            for part in candidate.get('content',{}).get('parts',[]):
                if part.get('thought') is True:continue
                if part.get('text'):text+=part['text']+'\n'
                inline=part.get('inlineData') or part.get('inline_data')
                if kind=='image' and inline and inline.get('data'):assets.append(save_image(inline['data'],job_id))
    elif protocol=='openai_image':
        for item in result.get('data',[]):
            if item.get('b64_json'):assets.append(save_image(item['b64_json'],job_id))
            elif item.get('url'):assets.append(media_url(item['url'],'image'))
    elif protocol=='minimax_image':
        for item in dig(result,'data.image_base64') or []:assets.append(save_image(item,job_id))
        if not assets:
            for item in dig(result,'data.image_urls') or []:assets.append(media_url(item,'image'))
    elif protocol=='minimax_speech':
        if dig(result,'data.audio'):assets.append(media_url(dig(result,'data.audio'),'audio'))
    return {'text':text.strip(),'assets':assets,**response_meta(p,result)}
def download_video(p,identity,job_id):
    req=urllib.request.Request(endpoint(p,'/videos/'+urllib.parse.quote(str(identity),safe='')+'/content'),headers=headers(p))
    name=job_id+'.mp4';target=storage.DATA/'media'/name;temp=target.with_suffix('.partial')
    try:
        with OPENER.open(req,timeout=150) as response,temp.open('wb') as output:
            if response.headers.get('Content-Type','').split(';')[0].strip() not in ('video/mp4','application/octet-stream'):raise ProviderError('视频下载未返回 MP4，请核对内容接口。')
            length=0
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                length+=len(chunk)
                if length>MAX_MEDIA:raise ProviderError('视频超过 512 MiB，请前往平台下载。')
                output.write(chunk)
        if not length:raise ProviderError('平台返回空视频。')
        with temp.open('rb') as source:
            if source.read(12)[4:8]!=b'ftyp':raise ProviderError('返回内容不是 MP4。')
        temp.replace(target)
        return {'type':'video','url':'/media/'+name,'local':True}
    except ProviderError:raise
    except Exception:raise ProviderError('视频已生成，但下载失败。可用平台任务 ID 到平台下载，请勿重复生成。') from None
    finally:
        if temp.exists():temp.unlink()
def poll(p,job,initial=None):
    identity=str(job['upstream_id']);protocol=p['protocol']
    if protocol=='openai_video':path,status_path,success,failure='/videos/'+urllib.parse.quote(identity,safe=''),'status',['completed'],['failed','cancelled']
    else:
        c=p['custom'];path=c['poll_path'].replace('{id}',urllib.parse.quote(identity,safe=''));status_path=c['status_path'];success,failure=c.get('success_values',[]),c.get('failure_values',[])
    deadline=time.monotonic()+POLL_TIMEOUT;response=initial;retries=0
    while time.monotonic()<deadline:
        if response is None:
            try:
                response=request(p,path);retries=0
            except ProviderError as ex:
                if ex.response:record_response(p,job['id'],ex.response)
                if ex.retryable and retries<5:
                    retries+=1;storage.update_job(job['id'],upstream_status='retrying');time.sleep(min(2**retries,15));continue
                raise
        raw_status=dig(response,status_path)
        metadata=record_response(p,job['id'],response)
        status='' if raw_status is None else str(raw_status).lower()
        storage.update_job(job['id'],upstream_status=status[:80],progress=response.get('progress') if isinstance(response.get('progress'),(int,float)) else None)
        if status in failure:raise ProviderError('平台任务失败：'+clean_error(json.dumps(response.get('error') or response.get('message') or status,ensure_ascii=False),p))
        if status in success:
            if protocol=='openai_video':return {'text':'','assets':[download_video(p,identity,job['id'])],**metadata}
            return {**extract(p,response,job['id']),**metadata}
        if not status:raise ProviderError('查询响应缺少状态字段，请核对映射。平台任务 ID 已保存。')
        time.sleep(POLL_SECONDS);response=None
    raise ProviderError('已等待 30 分钟。平台任务 ID 已保存，请到平台核对结果，不要直接重复提交。')
def execute(p,job,resume=False):
    if resume:return poll(p,job)
    path,body,multipart=build(p,job)
    if p['protocol']=='openai_speech':
        raw=request(p,path,body,binary=True)
        return {'text':'','assets':[save_audio(raw,job['id'])],**response_meta(p,{})}
    try:result=request(p,path,body,multipart)
    except ProviderError as ex:
        if ex.response:record_response(p,job['id'],ex.response)
        raise
    metadata=record_response(p,job['id'],result)
    if p['protocol'].startswith('minimax_') and dig(result,'base_resp.status_code') not in (None,0):
        raise ProviderError('MiniMax 返回错误：'+clean_error(dig(result,'base_resp.status_msg') or '请求失败',p),response=result)
    if p['protocol']=='openai_video':
        identity=result.get('id')
        if not identity:raise ProviderError('视频响应缺少任务 ID，请核对协议。')
        job=storage.update_job(job['id'],upstream_id=str(identity),status='polling')
        return poll(p,job,result)
    c=p.get('custom',{})
    if p['protocol']=='custom' and c.get('poll_path'):
        identity=dig(result,c.get('id_path',''))
        if identity is None or isinstance(identity,(dict,list)):raise ProviderError('响应没有有效任务 ID，请核对任务 ID 路径。')
        job=storage.update_job(job['id'],upstream_id=str(identity),status='polling')
        return poll(p,job)
    return {**extract(p,result,job['id']),**metadata}
def models(p):
    import model_catalog
    report=model_catalog.discover_saved(p)
    if not report['supported']:raise ValueError(report['caveat'])
    return [item['id'] for item in report['models']]
