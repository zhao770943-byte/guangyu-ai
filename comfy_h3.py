"""Local ComfyUI H3/ClipProj 4B adapter; one submission, resumable reads.

Uses native ComfyUI node contracts and the installed W4A8 + 4B configuration.
No server plugins, global queue operations, or arbitrary workflow execution.
"""
import re
import math
import secrets
import threading
import time
import urllib.parse
import urllib.request
import providers
import storage

MODEL='minimax-h3-local-8gb'
SIZES={'16:9':(608,352),'9:16':(352,608),'1:1':(448,448)}
DURATIONS={5:124,7:175,10:243,15:362}
PROFILES={'preview':SIZES,'detail':{'16:9':(864,480),'9:16':(480,864),'1:1':(640,640)}}
WEIGHTS={'UNETLoader':('unet_name','minimax_h3_fl2va_pruned_w4a8_mixed.safetensors'),
         'CLIPLoader':('clip_name','qwen3vl_4b_int8_convrot.safetensors'),
         'ClipProjApply':('projection','mmh3-4b-ClipProj-v3-mlp.safetensors'),
         'VAELoader':('vae_name','minimax_h3_video_vae_int8_convrot.safetensors')}
NODES=set(WEIGHTS)|{'MiniMaxH3SigmaShift','MiniMaxH3ImageToVideo','BasicGuider','KSamplerSelect',
                   'BasicScheduler','RandomNoise','SamplerCustomAdvanced','VAEDecodeTiled','CreateVideo','SaveVideo','LoadImage','ImageScale'}
SUBMIT_LOCK=threading.Lock()
POLL_SECONDS=3
POLL_TIMEOUT=1800

def validate_connection(p):
    u=urllib.parse.urlsplit(p.get('base_url',''))
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.path.rstrip('/') or u.username or u.password or u.query or u.fragment or not p.get('allow_local'):
        raise ValueError('本地 H3 仅连接本机 ComfyUI 根地址，例如 http://127.0.0.1:8188，并勾选允许本机 HTTP。')
    if p.get('model',MODEL)!=MODEL:raise ValueError('请选择自动检测到的本地 H3 8GB 工作流。')
    if p.get('extra'):raise ValueError('本地 H3 使用已适配工作流，请清空附加 JSON 参数。')

def local_request(p,path,payload=None,**kwargs):
    validate_connection(p)
    # Local workflows do not use cloud credentials, including accidentally saved keys.
    try:return providers.request({**p,'secret':''},path,payload,**kwargs)
    except providers.ProviderError as e:
        if e.code=='connection_interrupted':
            e.args=('无法连接本机 ComfyUI，或读取连接已中断。请确认 ComfyUI 已启动且地址、端口正确。'+('任务是否入队尚未确认，请勿直接重复生成。' if payload is not None else '已有任务只查询，不会重新生成。'),)
        raise

def inspect(p):
    info=local_request(p,'/object_info')
    missing=sorted(NODES-set(info))
    for node,(field,name) in WEIGHTS.items():
        choices=info.get(node,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
        if not isinstance(choices,list) or name not in choices:missing.append(name)
    optional=info.get('MiniMaxH3ImageToVideo',{}).get('input',{}).get('optional',{})
    if not {'first_frame','last_frame'}<=set(optional):missing.append('MiniMaxH3 首尾帧节点')
    if missing:raise ValueError('本机 H3 工作流尚未就绪，缺少：'+'、'.join(missing))
    return info

def discover(p):
    inspect(p)
    return {'models':[{'id':MODEL,'name':'MiniMax H3 · 本机 8GB','supported_kinds':['video'],
                       'model_kinds':['video'],'protocol':'comfy_h3','base_url':p['base_url'],
                       'model_constraints':{'kinds':['video'],'reason':'本机首帧 / 首尾帧图生视频。'}}],
            'source':'api','base_url':p['base_url'],'protocol':'comfy_h3','pages':1,
            'truncated':False,'supported':True,'caveat':'已检查本机节点与模型文件目录；支持约 5 / 7 / 10 / 15 秒、24 FPS 静音视频。长片使用快速预览档；细节档用于 5 / 7 秒，实际能否完成取决于可用内存。'}

def output_settings(j):
    """Follow source geometry by default; never stretch portrait input to landscape."""
    import uploads
    params=j.get('parameters') or {}
    level=params.get('resolution') or 'detail'
    ratio=params.get('aspect_ratio')
    if ratio:
        w,h=PROFILES[level][ratio]
    else:
        first=uploads.get(j['input_assets']['first_frame'])
        aspect=first['width']/first['height']
        area=608*352 if level=='preview' else 864*480
        w=math.sqrt(area*aspect);h=w/aspect
        scale=min(1,(608 if level=='preview' else 864)/max(w,h))
        w=max(32,round(w*scale/32)*32);h=max(32,round(h*scale/32)*32)
    return w,h,DURATIONS[j['seconds']]

def validate_job(p,j):
    validate_connection(p)
    if type(j.get('seconds')) is not int or j['seconds'] not in DURATIONS or j.get('size','auto')!='auto':raise ValueError('本地 H3 支持约 5、7、10、15 秒，像素尺寸保持自动。')
    assets=j.get('input_assets') or {}
    if not assets.get('first_frame'):raise ValueError('本地 H3 请先上传或从作品库选择一张首帧图片。')
    if assets.get('references'):raise ValueError('本地 H3 使用首帧 / 首尾帧，不接收多图参考列表。')
    params=j.get('parameters') or {}
    if set(params)-{'aspect_ratio','seed','resolution'}:raise ValueError('本地 H3 只支持当前显示的画幅、清晰度与随机种子参数。')
    ratio=params.get('aspect_ratio')
    if ratio and ratio not in SIZES:raise ValueError('本地 H3 支持跟随首帧、横屏、竖屏、方形画幅。')
    level=params.get('resolution') or 'detail'
    if level not in PROFILES:raise ValueError('本地 H3 清晰度请选择快速预览或细节优先。')
    if level=='detail' and j['seconds']>7:raise ValueError('8GB 细节优先档支持 5 / 7 秒；10 / 15 秒请选快速预览，或分镜生成后剪辑。')
    seed=params.get('seed',0)
    if type(seed) is not int or not 0<=seed<=2147483647:raise ValueError('随机种子应为 0–2147483647 的整数。')
    return output_settings(j)[:2]

def graph(j,images):
    w,h,frames=output_settings(j)
    nodes={}
    def add(identity,kind,**inputs):nodes[identity]={'class_type':kind,'inputs':inputs}
    add('1','UNETLoader',unet_name=WEIGHTS['UNETLoader'][1],weight_dtype='default')
    add('2','CLIPLoader',clip_name=WEIGHTS['CLIPLoader'][1],type='krea2',device='default')
    add('3','ClipProjApply',clip=['2',0],projection=WEIGHTS['ClipProjApply'][1])
    add('4','VAELoader',vae_name=WEIGHTS['VAELoader'][1])
    add('6','MiniMaxH3SigmaShift',model=['1',0],shift_video=12.0,shift_audio=3.0)
    add('17','LoadImage',image=images['first_frame'])
    # Native H3 stretches the first frame. Fit both anchors before entering it.
    add('19','ImageScale',image=['17',0],upscale_method='lanczos',width=w,height=h,crop='center')
    add('8','MiniMaxH3ImageToVideo',clip=['3',0],vae=['4',0],prompt=j['prompt'],width=w,height=h,length=frames,first_frame=['19',0])
    if images.get('last_frame'):
        add('18','LoadImage',image=images['last_frame'])
        add('20','ImageScale',image=['18',0],upscale_method='lanczos',width=w,height=h,crop='center')
        nodes['8']['inputs']['last_frame']=['20',0]
    add('9','BasicGuider',model=['6',0],conditioning=['8',0])
    add('10','KSamplerSelect',sampler_name='euler')
    add('11','BasicScheduler',model=['6',0],scheduler='simple',steps=20,denoise=1.0)
    add('12','RandomNoise',noise_seed=(j.get('parameters') or {}).get('seed',secrets.randbelow(2147483648)))
    add('13','SamplerCustomAdvanced',noise=['12',0],guider=['9',0],sampler=['10',0],sigmas=['11',0],latent_image=['8',1])
    add('14','VAEDecodeTiled',samples=['13',0],vae=['4',0],tile_size=256,overlap=64,temporal_size=32,temporal_overlap=8)
    add('15','CreateVideo',images=['14',0],fps=24.0,bit_depth='auto',color_space='sRGB',codec='none')
    add('16','SaveVideo',video=['15',0],filename_prefix='video/Guangyu/'+j['id'],format='mp4',**{'format.codec':'auto'})
    return nodes

def safe_component(value,folder=False):
    if not isinstance(value,str) or (not value and not folder):raise ValueError('ComfyUI 返回的素材路径无效。')
    value=value.replace('\\','/')
    if value.startswith('/') or ':' in value or any(ord(c)<32 for c in value) or any(v in ('.','..') for v in value.split('/')) or (not folder and '/' in value):raise ValueError('ComfyUI 返回的素材路径无效。')
    return value

def execute(p,j,resume=False):
    validate_connection(p)
    if resume:return poll(p,j)
    validate_job(p,j)
    with SUBMIT_LOCK:
        inspect(p)
        q=local_request(p,'/queue')
        if q.get('queue_running') or q.get('queue_pending'):raise ValueError('本机 ComfyUI 正在执行或排队其他任务，请等待完成后再生成。尚未提交本次任务。')
        images={}
        for slot in ('first_frame','last_frame'):
            identity=(j.get('input_assets') or {}).get(slot)
            if not identity:continue
            result=local_request(p,'/upload/image',{'image':providers.FilePart(identity),'type':'input','overwrite':'false'},multipart=True)
            name=safe_component(result.get('name'));folder=safe_component(result.get('subfolder',''),True)
            images[slot]=(folder+'/' if folder else '')+name
        result=local_request(p,'/prompt',{'prompt':graph(j,images),'client_id':'guangyu-'+j['id']})
        identity=result.get('prompt_id')
        if not isinstance(identity,str) or not re.fullmatch(r'[a-fA-F0-9-]{32,36}',identity):raise providers.ProviderError('ComfyUI 未返回有效任务 ID，请到本机 ComfyUI 核对队列，勿重复提交。',uncertain=True)
        j=storage.update_job(j['id'],upstream_id=identity,status='polling',upstream_status='queued')
    return poll(p,j)

def download(p,j,item):
    name=safe_component(item.get('filename'));folder=safe_component(item.get('subfolder',''),True)
    if item.get('type')!='output' or not name.lower().endswith('.mp4'):raise providers.ProviderError('本机 H3 没有返回有效 MP4 输出。')
    query=urllib.parse.urlencode({'filename':name,'subfolder':folder,'type':'output'})
    path=storage.DATA/'media'/(j['id']+'-0.mp4');temp=path.with_suffix('.part')
    try:
        req=urllib.request.Request(providers.endpoint(p,'/view?'+query))
        with providers.OPENER.open(req,timeout=60) as r,temp.open('wb') as f:
            total=0
            while chunk:=r.read(1024*1024):
                total+=len(chunk)
                if total>providers.MAX_MEDIA:raise ValueError('输出超过 512 MiB 上限。')
                f.write(chunk)
        with temp.open('rb') as f:
            if f.read(12)[4:8]!=b'ftyp':raise ValueError('输出并非 MP4 文件。')
        import av
        with av.open(str(temp)) as container:
            stream=container.streams.video[0]
            w,h=stream.width,stream.height
            duration=float(stream.duration*stream.time_base) if stream.duration is not None else None
        temp.replace(path)
    except Exception:
        raise providers.ProviderError('本机 H3 已完成，但视频保存失败。请继续查询原任务重试保存，不要重新生成。') from None
    finally:temp.unlink(missing_ok=True)
    # Actual output metadata also handles resumed jobs from older profile versions.
    return {'text':'','assets':[{'type':'video','local':True,'url':'/media/'+path.name,'width':w,'height':h,'duration_seconds':duration}]}

def poll(p,j):
    identity=j.get('upstream_id','')
    if not re.fullmatch(r'[a-fA-F0-9-]{32,36}',identity):raise ValueError('本机 ComfyUI 任务 ID 无效。')
    deadline=time.monotonic()+POLL_TIMEOUT;missing=0
    while time.monotonic()<deadline:
        try:history=local_request(p,'/history/'+identity).get(identity)
        except providers.ProviderError as e:
            raise providers.ProviderError(str(e),uncertain=True,code=e.code) from None
        if history:
            status=history.get('status') or {}
            if status.get('status_str')=='error':
                detail=''
                for event in status.get('messages',[]):
                    if isinstance(event,list) and len(event)==2 and event[0] in ('execution_error','execution_interrupted') and isinstance(event[1],dict):
                        detail=str(event[1].get('exception_message') or event[0])[:500]
                storage.update_job(j['id'],upstream_status='failed')
                raise providers.ProviderError('本机 H3 执行失败：'+(detail or '请查看 ComfyUI 日志。'),code='comfy_execution_failed')
            outputs=(history.get('outputs') or {}).get('16',{})
            items=outputs.get('images') or outputs.get('videos') or []
            if status.get('completed') and status.get('status_str')=='success':
                storage.update_job(j['id'],upstream_status='completed')
                if not items:raise providers.ProviderError('ComfyUI 任务已完成，但没有视频输出。')
                return download(p,j,items[0])
        try:q=local_request(p,'/queue')
        except providers.ProviderError as e:raise providers.ProviderError(str(e),uncertain=True,code=e.code) from None
        running=any(isinstance(row,list) and len(row)>1 and row[1]==identity for row in q.get('queue_running',[]))
        pending=any(isinstance(row,list) and len(row)>1 and row[1]==identity for row in q.get('queue_pending',[]))
        missing=0 if running or pending or history else missing+1
        if missing>=3:raise providers.ProviderError('ComfyUI 队列与历史中已找不到原任务，可能服务已重启或历史被清理。请核对 ComfyUI 输出目录；本机不会自动重发。',uncertain=True)
        storage.update_job(j['id'],upstream_status='in_progress' if running else 'queued',progress=None)
        time.sleep(POLL_SECONDS)
    raise providers.ProviderError('本机 H3 等待超过 30 分钟。任务 ID 已保存，可继续查询原任务，不会自动重发。',uncertain=True)
