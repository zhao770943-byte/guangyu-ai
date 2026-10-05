"""Version-bound editorial records. No provider calls and no implicit approvals."""
import copy
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
import storage
import uploads

SHOT_CHECKS = ('identity', 'prop', 'space', 'crowd', 'eyeline', 'action', 'bridge')
DELIVERY_CHECKS = ('picture', 'continuity', 'dialogue', 'pronunciation', 'lip_sync', 'ambience', 'mix', 'cover')
CONTRACT_FIELDS = ('start', 'end', 'eyeline', 'crowd', 'bridge', 'beats', 'avoid')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def clean(value, name, limit=1800, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(name+'内容为空或过长。')
    return value.strip()


def book(p):
    return p.get('production_book') or {}


def pairs(p):
    return [('shot:'+e['id']+':'+s['id'], e, s, i) for e in (p.get('plan') or {}).get('episodes', []) for i,s in enumerate(e.get('shots', []))]


def find(p, key):
    value = next((v for v in pairs(p) if v[0] == key), None)
    if not value:
        raise ValueError('镜头不存在。')
    return value


@lru_cache(maxsize=512)
def file_hash(filename, size, mtime):
    h = hashlib.sha256()
    with Path(filename).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def image_version(identity):
    if not identity:
        return None
    r = uploads.get(identity)
    f = storage.DATA/'uploads'/r['filename']; stat = f.stat()
    return [identity, file_hash(str(f), stat.st_size, stat.st_mtime_ns)]


def fingerprint(p, key):
    _,e,s,i = find(p,key)
    previous = e['shots'][i-1] if i else None
    following = e['shots'][i+1] if i+1 < len(e['shots']) else None
    # The motion auditor can polish video_prompt later; storyboard approval binds
    # narrative facts, pixels, references and explicit staging, not wording alone.
    facts = {k:v for k,v in s.items() if k != 'video_prompt'}
    image = image_version(p.get('images', {}).get(key))
    if not image:
        raise ValueError('先生成或选择本镜分镜图。')
    assets = {a['id']:a for a in p['plan']['assets']}
    refs = {a:[image_version(p.get('locked_assets', {}).get(a)), assets.get(a)] for a in s.get('asset_ids', [])}
    if any(not v[0] for v in refs.values()):
        raise ValueError('本镜引用的定稿尚未锁定。')
    prev = None
    if previous:
        prev_key = 'shot:'+e['id']+':'+previous['id']
        prev = [image_version(p.get('images', {}).get(prev_key)), {k:v for k,v in previous.items() if k != 'video_prompt'}, book(p).get('contracts', {}).get(prev_key)]
        if not prev[0]:
            raise ValueError('前一镜分镜图尚未完成，无法确认衔接。')
    nxt = None
    if following:
        next_key = 'shot:'+e['id']+':'+following['id']
        nxt = [image_version(p.get('images', {}).get(next_key)), {k:v for k,v in following.items() if k != 'video_prompt'}, book(p).get('contracts', {}).get(next_key)]
        if not nxt[0]:
            raise ValueError('后一镜分镜图尚未完成，无法确认衔接。')
    return digest([image, facts, refs, prev, nxt, book(p).get('contracts', {}).get(key), p['ratio']])


def shot_state(p, key):
    review = book(p).get('storyboards', {}).get(key)
    try:
        current = fingerprint(p,key)
    except (ValueError, OSError) as exc:
        return {'status':'missing', 'reason':str(exc), 'fingerprint':None}
    ok = bool(review and review.get('fingerprint') == current and all(review.get('checks', {}).get(k) is True for k in SHOT_CHECKS))
    return {'status':'approved' if ok else 'stale' if review else 'pending', 'fingerprint':current,
            'reason':('AI 已审当前版本' if review.get('source') == 'ai_visual' else '当前版本已审') if ok else '图像、定稿或衔接已变化' if review else '待逐镜审图'}


def require_shots(p, only=None):
    if not book(p).get('enabled'):
        return
    if any(not i.get('resolved') and (not only or not i.get('shot') or i['shot'] == only) for i in book(p).get('issues', [])):
        raise ValueError('仍有未关闭的制作问题，未提交视频。')
    pending = [s['title'] for key,e,s,i in pairs(p) if (not only or key == only) and shot_state(p,key)['status'] != 'approved']
    if pending:
        raise ValueError('分镜与连续性尚未通过，未提交视频：'+'、'.join(pending[:4]))


def contract_prompt(p, key):
    c = book(p).get('contracts', {}).get(key)
    if not c:
        return ''
    labels = {'start':'首帧实际状态','end':'镜尾状态','eyeline':'视线与方向','crowd':'背景人物调度','bridge':'邻镜衔接','beats':'有效片段动作节拍','avoid':'禁止额外动作'}
    mode = {'dub':'后期配音：本镜不生成清楚对白；保留自然环境声，嘴部动作服从对白节拍。', 'native':'生成同期声，清楚对白只使用本镜剧本，不自行加台词。', 'silent':'无对白，无配乐，只生成画面。'}[c['sound_mode']]
    return '\n已确认的拍摄约定（不得被语言润色覆盖）：\n'+'\n'.join(labels[k]+'：'+c[k] for k in CONTRACT_FIELDS)+'\n'+mode


def film_fingerprint(p):
    films = []
    for e in (p.get('plan') or {}).get('episodes', []):
        j = storage.get('jobs', p.get('films', {}).get(e['id'], ''))
        if not j or j.get('status') != 'succeeded':
            raise ValueError('本集成片尚未完成。')
        videos = [a for a in j.get('result', {}).get('assets', []) if a.get('type') == 'video' and a.get('local')]
        if not videos:
            raise ValueError('成片尚未保存在本机。')
        hashes=[]
        for video in videos:
            url=video.get('url','')
            if not re.fullmatch(r'/media/[a-zA-Z0-9_-]+\.(mp4|webm|mov|mkv)',url):
                raise ValueError('成片本机地址无效。')
            f=storage.DATA/'media'/url.rsplit('/',1)[1]
            if not f.is_file() or not f.stat().st_size:
                raise ValueError('成片文件缺失。')
            stat=f.stat();hashes.append(file_hash(str(f),stat.st_size,stat.st_mtime_ns))
        films.append([j['id'], videos, hashes])
    if not films:
        raise ValueError('还没有可验收的成片。')
    return digest([films, book(p).get('voices', []), book(p).get('mix_notes', ''), book(p).get('issues', [])])


def summary(p):
    b = book(p); shots = {key:shot_state(p,key) for key,e,s,i in pairs(p)}
    delivery = False
    try:
        delivery = bool(b.get('delivery', {}).get('fingerprint') == film_fingerprint(p))
    except ValueError:
        pass
    return {'enabled':b.get('enabled', False), 'shots':shots, 'approved':sum(s['status']=='approved' for s in shots.values()),
            'total':len(shots), 'delivery_approved':delivery, 'open_issues':sum(not i.get('resolved') for i in b.get('issues', []))}


def apply(p, body):
    action = body['action']
    # A failed validation must not partially mutate a project.
    b = copy.deepcopy(book(p))
    if action == 'studio_enable':
        if not p.get('paused') and p['phase'] not in ('draft','script_review','asset_review','shot_review','video_review','complete'):
            raise ValueError('请先暂停后续提交，再启用专业制作流程。')
        b['enabled'] = True
        p['review_storyboards'] = p['review_videos'] = True
        p['review_standard'] = 'five_dimensions'
    elif action == 'studio_contract':
        key = body.get('slot'); find(p,key)
        if p['phase'] not in ('draft','script_review','asset_review','shot_review','video_review','complete') and not p['paused']:
            raise ValueError('请先暂停后续提交，再修改镜头约定。')
        value = body.get('contract')
        if not isinstance(value,dict):
            raise ValueError('镜头约定格式错误。')
        c = {k:clean(value.get(k,''), k) for k in CONTRACT_FIELDS}
        c['sound_mode'] = value.get('sound_mode','dub')
        if c['sound_mode'] not in ('dub','native','silent'):
            raise ValueError('请选择声音方案。')
        b.setdefault('contracts', {})[key] = c
    elif action == 'studio_review_shot':
        key = body.get('slot'); find(p,key)
        c = b.get('contracts', {}).get(key, {})
        if any(not c.get(k) for k in CONTRACT_FIELDS):
            raise ValueError('请先保存完整镜头约定；无人物或无衔接时写明不适用及原因。')
        current = fingerprint(p,key)
        if body.get('fingerprint') != current:
            raise ValueError('图像或镜头约定已换版，请刷新后重审。')
        if body.get('inspected') is not True or not isinstance(body.get('checks'),dict) or any(body['checks'].get(k) is not True for k in SHOT_CHECKS):
            raise ValueError('请实际查看本镜与邻镜，并完成七项审图。')
        b.setdefault('storyboards', {})[key] = {'fingerprint':current, 'checks':{k:True for k in SHOT_CHECKS},
            'notes':clean(body.get('notes',''), '审图依据', required=True), 'time':storage.now(), 'source':'recorded_visual_review'}
    elif action == 'studio_sound':
        voices = body.get('voices', [])
        if not isinstance(voices,list) or len(voices)>32 or any(not isinstance(v,dict) for v in voices):
            raise ValueError('声线表最多32项。')
        known = {a['id'] for a in (p.get('plan') or {}).get('assets',[]) if a['kind']=='character'} | {'voice:narrator','voice:announcer','voice:crowd'}
        rows=[]; seen=set()
        for v in voices:
            aid=v.get('asset_id')
            if aid not in known or aid in seen:
                raise ValueError('声线人物无效或重复。')
            seen.add(aid)
            row={k:clean(v.get(k,''),k,1200) for k in ('voice','pronunciation','direction','audio_job_id')};row['asset_id']=aid
            if row['audio_job_id']:
                from production_readiness import audio_reference
                if not audio_reference(row['audio_job_id']):
                    raise ValueError('试听必须选择未删除、文件存在的本机成功音频。请重新选择。')
            rows.append(row)
        b['voices']=rows;b['mix_notes']=clean(body.get('mix_notes',''),'混音说明',4000)
    elif action == 'studio_issue':
        issue={'id':storage.uid(),'shot':clean(body.get('shot',''),'镜头编号',120),'category':clean(body.get('category',''),'问题类型',60,True),'notes':clean(body.get('notes',''),'问题说明',1800,True),'resolved':False,'time':storage.now()}
        if issue['shot']:find(p,issue['shot'])
        if len(b.get('issues',[]))>=300:raise ValueError('问题记录已达300条，请导出归档。')
        b.setdefault('issues',[]).append(issue)
    elif action == 'studio_resolve':
        issue=next((i for i in b.get('issues',[]) if i['id']==body.get('issue_id')),None)
        if not issue:raise ValueError('问题记录不存在。')
        issue['resolution']=clean(body.get('resolution',''),'修复依据',1800,True);issue['resolved']=True;issue['resolved_at']=storage.now()
    elif action == 'studio_delivery':
        if body.get('watched') is not True or not isinstance(body.get('checks'),dict) or any(body['checks'].get(k) is not True for k in DELIVERY_CHECKS):
            raise ValueError('请完整观看本版成片，完成交付检查。')
        if any(not i.get('resolved') for i in b.get('issues',[])):
            raise ValueError('仍有未关闭的制作问题。')
        current=film_fingerprint(p)
        if current!=body.get('fingerprint'):raise ValueError('交付版本已变化，请重新查看。')
        if b.get('delivery'):
            b.setdefault('delivery_history', []).append(copy.deepcopy(b['delivery']))
        b['delivery']={'fingerprint':current,'time':storage.now(),'checks':{k:True for k in DELIVERY_CHECKS},'notes':clean(body.get('notes',''),'交付依据',3000,True)}
        p['final_user_approved']=True
    else:
        raise ValueError('未知制作手册操作。')
    p['production_book']=b
    if b.get('delivery') and not summary(p)['delivery_approved']:
        p['final_user_approved']=False
    p.setdefault('history',[]).append({'time':storage.now(),'event':action,'slot':body.get('slot',''),'changes':'制作手册已保存；本操作未提交模型任务'})


def public_state(p):
    state=summary(p)
    try:state['film_fingerprint']=film_fingerprint(p)
    except ValueError:state['film_fingerprint']=None
    return state
