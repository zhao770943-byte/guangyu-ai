"""Durable storyboard preparation using normal image jobs and bounded dispatch."""
import base64
import json
import re
import capabilities
import storage
import uploads
import work_library

ACTIVE={'queued','submitting','polling'}
RATIOS={'9:16','16:9','1:1','3:2','2:3','4:3','3:4'}


def require(identity):
    if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('分镜项目 ID 无效。')
    board=storage.get('storyboards',identity)
    if not board:raise ValueError('分镜项目不存在。')
    return board


def jobs(board):
    identities=[board.get('master_job_id')]+[s.get('job_id') for s in board['shots']]
    return [j for identity in identities if identity and (j:=storage.get('jobs',identity))]


def busy(board):
    return any(j['status'] in ACTIVE or j.get('archive_status')=='pending' for j in jobs(board))


def public(board):
    result={k:v for k,v in board.items() if k!='requests'}
    result['jobs']=[storage.public_job(j) for j in jobs(board)]
    result['busy']=busy(board)
    result['master_asset']=uploads.get(board['master_upload_id']) if board.get('master_upload_id') else None
    if result['master_asset']:result['master_asset']={k:v for k,v in result['master_asset'].items() if k!='filename'}
    return result


def list_projects():
    return [{k:b[k] for k in ('id','title','updated_at')} for b in storage.items('storyboards',200)]


def text(value,label,maximum,empty=False):
    if not isinstance(value,str) or len(value)>maximum or (not empty and not value.strip()):raise ValueError(f'{label}需为 1–{maximum} 字。')
    return value.strip()


def check_version(board,body):
    if body.get('version')!=board['version']:raise ValueError('项目已更新，请重新载入后操作，避免覆盖新内容。')


def touch(board):
    board['version']+=1;board['updated_at']=storage.now()
    return board


def save(body):
    with storage.LOCK:
        old=require(body['id']) if body.get('id') else None
        if old:
            check_version(old,body)
            if busy(old):raise ValueError('图片仍在生成或保存，请完成后修改项目。')
        shots=body.get('shots')
        if not isinstance(shots,list) or not 1<=len(shots)<=8:raise ValueError('每个项目支持 1–8 个镜头。')
        clean=[];seen=set();previous={s['id']:s for s in old['shots']} if old else {}
        for i,s in enumerate(shots):
            if not isinstance(s,dict):raise ValueError('镜头格式无效。')
            identity=s.get('id') or storage.uid()
            if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity) or identity in seen:raise ValueError('镜头 ID 无效或重复。')
            seen.add(identity)
            clean.append({'id':identity,'title':text(s.get('title'),f'镜头 {i+1} 标题',80),
                          'prompt':text(s.get('prompt'),f'镜头 {i+1} 描述',4000),
                          'job_id':previous.get(identity,{}).get('job_id')})
        ratio=body.get('ratio','9:16')
        if ratio not in RATIOS:raise ValueError('分镜比例无效。')
        board={**(old or {'id':storage.uid(),'version':0,'master_job_id':None,'master_upload_id':None,'requests':{}}),
               'title':text(body.get('title'),'项目名称',80),'story':text(body.get('story'),'创意脚本',16000),
               'master_prompt':text(body.get('master_prompt',''),'定稿图补充描述',6000,empty=True),
               'provider_id':text(body.get('provider_id'),'图像模型',80),'ratio':ratio,'shots':clean}
        storage.put('storyboards',touch(board))
        return public(board)


def image_from_job(identity,asset_index=None):
    job=storage.get('jobs',identity) if isinstance(identity,str) else None
    if not job or job['kind']!='image' or job['status']!='succeeded' or job.get('work_deleted_at'):raise ValueError('这张图片尚未生成成功或已删除。')
    assets=job.get('result',{}).get('assets',[])
    if asset_index is None:
        asset=next((a for a in assets if a.get('type')=='image' and a.get('local')),None)
    else:
        if type(asset_index) is not int or not 0<=asset_index<len(assets):raise ValueError('请选择有效的作品图片。')
        asset=assets[asset_index]
        if asset.get('type')!='image' or not asset.get('local'):raise ValueError('请选择已保存到本机的图片。')
    if not asset:raise ValueError('图片尚未保存到本机，请等待保存完成，或在作品库重试保存原图。')
    path=work_library.local_path(asset['url'])
    if not path.is_file() or path.stat().st_size>uploads.MAX_BYTES:raise ValueError('图片不存在或超过参考图的 10 MiB 上限，请换用较小图片。')
    return uploads.save({'name':'分镜素材-'+identity[:8]+path.suffix,'data_base64':base64.b64encode(path.read_bytes()).decode()})


def library_image(body):
    # Copy verified server-owned media; never accept arbitrary paths or remote URLs.
    if type(body.get('asset_index')) is not int:raise ValueError('请选择作品中的具体图片。')
    with storage.LOCK:
        return image_from_job(body.get('job_id'),body['asset_index'])


def confirm(body,active_lock):
    with active_lock,storage.LOCK:
        board=require(body.get('id'));check_version(board,body)
        if busy(board):raise ValueError('请等待当前图片生成和保存完成。')
        if not board.get('master_job_id'):raise ValueError('请先生成定稿图。')
        if board.get('confirmed_job_id')==board['master_job_id'] and board.get('master_upload_id'):return public(board)
        asset=image_from_job(board['master_job_id'])
        board.update(master_upload_id=asset['id'],confirmed_job_id=board['master_job_id'])
        for shot in board['shots']:shot['job_id']=None
        storage.put('storyboards',touch(board));return public(board)


def prompt_for(board,shot=None):
    common=f"项目创意：\n{board['story']}\n人物、服装与场景要求：\n{board['master_prompt']}\n画幅：{board['ratio']}。"
    if shot:
        return common+f"\n仅生成以下镜头的一张独立静态分镜图：{shot['title']}\n{shot['prompt']}\n必须以输入的定稿参考图为共同依据，保持人物身份、脸部、发型、服装、配饰、色彩和场景风格一致。根据此镜头调整姿态、景别和机位。不要照抄参考图的构图，不要表现整段故事。单一瞬间，无分屏、无拼贴、无字幕、无水印。"
    return common+'\n请生成一张用于视频制作的视觉定稿图。提炼创意中的主要人物、服装、配饰、环境与光线，以清晰的单一静态画面呈现。有人物时优先完整全身构图，展示关键服装与道具，姿态自然。忽略脚本中的对话、声音、时间顺序和运镜指令，不要把多个事件拼在一张图里。无分屏、无字幕、无文字标签、无水印。'


def generate(body,prepare,dispatch,active,active_lock):
    with active_lock,storage.LOCK:
        board=require(body.get('id'))
        token=body.get('request_id','')
        if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('生成请求标识无效。')
        if token in board['requests']:return public(board)
        check_version(board,body)
        if busy(board):raise ValueError('当前项目仍有图片任务，请等待完成后再提交。')
        p=storage.get('providers',board['provider_id'])
        if not p or p['kind']!='image':raise ValueError('请为分镜选择有效的图像模型。')
        if p.get('extra',{}).get('n',1)!=1:raise ValueError('分镜每个镜头生成一张图，请将该连接的附加参数 n 设为 1 或移除。')
        stage=body.get('stage')
        if stage not in ('master','shots','shot'):raise ValueError('生成阶段无效。')
        if stage!='master':
            if not board.get('master_upload_id'):raise ValueError('请先确认定稿图，再生成分镜。')
            if not capabilities.effective(p)['reference_images']:raise ValueError('该图像模型不支持参考图，请切换支持参考图创作的图像连接。')
            uploads.get(board['master_upload_id'])
        selected=[None] if stage=='master' else [s for s in board['shots'] if stage=='shots' or s['id']==body.get('shot_id')]
        if not selected:raise ValueError('镜头不存在。')
        if len(active)+len(selected)>12:raise ValueError('本机队列空间不足，请等待其他任务完成后再批量提交。')
        prepared=[]
        for shot in selected:
            params={'n':1} if capabilities.effective(p)['batch'] else {}
            if capabilities.effective(p)['aspect_ratio']:params['aspect_ratio']=board['ratio']
            job=prepare({'provider_id':p['id'],'prompt':prompt_for(board,shot),'size':'auto',
                         'parameters':params,'input_assets':{'references':[board['master_upload_id']] if shot else []}},prepare_only=True)
            job.update(storyboard_id=board['id'],storyboard_stage=stage,storyboard_shot_id=shot['id'] if shot else None)
            prepared.append(job)
            if shot:shot['job_id']=job['id']
            else:board.update(master_job_id=job['id'],master_upload_id=None,confirmed_job_id=None)
        board['requests'][token]=[j['id'] for j in prepared]
        touch(board)
        # Persist every job and the project links together before dispatch.
        # Recovery never replays an unsubmitted image POST after a restart.
        with storage.connect() as db:
            for j in prepared:db.execute('INSERT INTO jobs VALUES (?,?,?)',(j['id'],j['created_at'],json.dumps(j,ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO storyboards VALUES (?,?,?)',(board['id'],board['updated_at'],json.dumps(board,ensure_ascii=False)))
        for job in prepared:dispatch(job)
        return public(board)


def transfer(body):
    with storage.LOCK:
        board=require(body.get('id'))
        identity=body.get('job_id')
        if identity not in [j['id'] for j in jobs(board)]:raise ValueError('图片不属于当前分镜项目。')
        return image_from_job(identity)
