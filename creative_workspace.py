"""Saved drafts, reusable local images and explicit project collections."""
import copy
import re
import math
import storage
import uploads
import capabilities

TABLE = 'workspace_items'


def text(value, limit, label):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(label + '格式无效或过长。')
    return value.strip()


def require(key, category=None):
    if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{32}', key):
        raise ValueError('记录ID无效。')
    value = storage.get(TABLE, key)
    if not value or category and value['category'] != category:
        raise ValueError('记录不存在，请刷新。')
    return value


def collection(key):
    if not key:
        return ''
    if not isinstance(key, str):
        raise ValueError('合集无效。')
    if ':' in key:
        prefix, identity = key.split(':', 1)
        table = {'visual': 'visual_projects', 'storyboard': 'storyboards', 'novel': 'novel_projects'}.get(prefix)
        if not table or not re.fullmatch(r'[a-f0-9]{32}', identity) or not storage.get(table, identity):
            raise ValueError('项目合集不存在。')
    else:
        require(key, 'collection')
    return key


def asset(key):
    return {k: v for k, v in uploads.get(key).items() if k != 'filename'}


def draft_data(body):
    kind = body.get('kind')
    if kind not in ('image', 'video'):
        raise ValueError('草稿类型无效。')
    value = body.get('draft')
    if not isinstance(value, dict):
        raise ValueError('草稿格式无效。')
    prompt = text(value.get('prompt', ''), 32000, '剧本描述')
    mode = value.get('mode', 'text')
    if mode not in ('text', 'reference', 'first', 'first_last') or kind == 'image' and mode not in ('text', 'reference'):
        raise ValueError('草稿模式无效。')
    size = value.get('size', 'auto')
    if not isinstance(size, str) or size != 'auto' and not re.fullmatch(r'\d{2,5}x\d{2,5}', size):
        raise ValueError('草稿尺寸无效。')
    seconds = value.get('seconds', 4)
    if type(seconds) != int or not 1 <= seconds <= 120:
        raise ValueError('草稿时长无效。')
    params = value.get('parameters', {})
    if not isinstance(params, dict) or set(params) - set(capabilities.PARAMETERS):
        raise ValueError('草稿参数无效。')
    for v in params.values():
        if not isinstance(v, (str, int, float, bool, type(None))) or isinstance(v, str) and len(v) > 4000 or isinstance(v, float) and not math.isfinite(v):
            raise ValueError('草稿参数值无效。')
    inputs = value.get('assets', {})
    if not isinstance(inputs, dict):
        raise ValueError('草稿素材无效。')
    refs = inputs.get('references', [])
    if not isinstance(refs, list) or len(refs) > 9:
        raise ValueError('参考图片最多9张。')
    clean = {'references': refs[:], 'first_frame': inputs.get('first_frame'), 'last_frame': inputs.get('last_frame')}
    for key in refs + [clean['first_frame'], clean['last_frame']]:
        if key is not None:
            uploads.get(key)
    provider = body.get('provider_id') or ''
    if provider:
        p = storage.get('providers', provider)
        if not p or p['kind'] != kind:
            raise ValueError('草稿模型不存在或类型不符。')
    return {'kind': kind, 'provider_id': provider, 'draft': {'prompt': prompt, 'mode': mode, 'size': size, 'seconds': seconds,
            'parameters': copy.deepcopy(params), 'assets': clean, 'collection_id': collection(value.get('collection_id', ''))}}


def save(body, category):
    with storage.LOCK:
        old = require(body['id'], category) if body.get('id') else None
        if old and body.get('version') != old['version']:
            raise ValueError('记录已在其他窗口更新，请刷新后再保存。')
        title = text(body.get('title', ''), 120, '名称')
        if not title:
            raise ValueError('请输入名称。')
        value = {'id': old['id'] if old else storage.uid(), 'category': category, 'title': title,
                 'version': (old or {}).get('version', 0) + 1, 'created_at': (old or {}).get('created_at', storage.now()), 'updated_at': storage.now()}
        if category == 'draft':
            value.update(draft_data(body))
        elif category == 'material':
            value['upload_id'] = asset(body.get('upload_id'))['id']
        elif category == 'collection':
            value['job_ids'] = (old or {}).get('job_ids', [])
        else:
            raise ValueError('记录类型无效。')
        storage.put(TABLE, value)
        return public(value)


def public(value):
    result = copy.deepcopy(value)
    ids = [value['upload_id']] if value['category'] == 'material' else []
    if value['category'] == 'draft':
        inputs = value['draft']['assets']
        ids = list(dict.fromkeys(inputs['references'] + [v for v in (inputs['first_frame'], inputs['last_frame']) if v]))
    result['assets'] = []
    for key in ids:
        try:
            result['assets'].append(asset(key))
        except ValueError:
            pass
    return result


def listing():
    records = storage.items(TABLE, -1)
    collections = [public(v) for v in records if v['category'] == 'collection']
    assignments = {job: v['id'] for v in collections for job in v['job_ids']}
    for table, prefix in (('visual_projects', 'visual'), ('storyboards', 'storyboard'), ('novel_projects', 'novel')):
        for p in storage.items(table, -1):
            key = prefix + ':' + p['id']
            collections.append({'id': key, 'title': p['title'], 'automatic': True})
            ids = [j for n in p.get('nodes', []) for j in n.get('job_ids', [])]
            ids += [p.get('master_job_id')] + [s.get('job_id') for s in p.get('shots', [])]
            for job in ids:
                if job:
                    assignments.setdefault(job, key)
    return {'drafts': [public(v) for v in records if v['category'] == 'draft'],
            'materials': [public(v) for v in records if v['category'] == 'material'],
            'collections': collections, 'assignments': assignments}


def remove(body, category):
    with storage.LOCK:
        item = require(body.get('id'), category)
        if body.get('version') != item['version']:
            raise ValueError('记录已变化，请刷新。')
        # Remove only the saved entry; shared uploads remain for other drafts/jobs.
        with storage.connect() as db:
            db.execute('DELETE FROM workspace_items WHERE id=?', (item['id'],))
    return {'ok': True}


def assign(body):
    with storage.LOCK:
        target = require(body.get('collection_id'), 'collection')
        jobs = body.get('job_ids')
        if not isinstance(jobs, list) or not 1 <= len(jobs) <= 500 or any(not isinstance(j, str) for j in jobs):
            raise ValueError('请选择1–500条作品。')
        for key in jobs:
            j = storage.get('jobs', key)
            if not j or j.get('status') != 'succeeded' or j.get('work_deleted_at') or not j.get('result', {}).get('assets'):
                raise ValueError('选中的作品已不可用。')
        changed = []
        for item in storage.items(TABLE, -1):
            if item['category'] != 'collection':
                continue
            ids = [j for j in item['job_ids'] if j not in jobs]
            if item['id'] == target['id']:
                ids += list(dict.fromkeys(jobs))
            if ids != item['job_ids']:
                item.update(job_ids=ids, version=item['version'] + 1, updated_at=storage.now())
                changed.append(item)
        # One transaction so a move cannot leave an item in two manual collections.
        import json
        with storage.connect() as db:
            for item in changed:
                db.execute('UPDATE workspace_items SET payload=?,updated_at=? WHERE id=?', (json.dumps(item, ensure_ascii=False), item['updated_at'], item['id']))
        return listing()
