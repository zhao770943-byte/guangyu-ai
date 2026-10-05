"""Persisted production team. Connections hold secrets; roles hold only connection IDs."""
import copy
import hashlib
import json
import storage
import uploads

ID = '00000000000000000000000000002701'
VISION_PROTOCOLS = {'openai_chat', 'openai_responses', 'anthropic', 'gemini'}
ROLES = {
    'director': {'name': '导演 AI', 'task': '拆解原著，规划集数、资产与叙事重点', 'instruction': '你是导演。忠于原著，明确角色与场景，控制改编范围，不靠重复镜头填满时长。'},
    'writer': {'name': '编剧 AI', 'task': '编写分集剧本、镜头动作与对白', 'instruction': '你是编剧。把原文转为可拍摄的动作，每镜只承载一个主要事件，保持节奏和因果。'},
    'costume': {'name': '定妆审图 AI', 'task': '对照原始稿图检查人物、服装与画风', 'instruction': '你是定妆与视觉连续性审查员。只根据提供的图像像素与文字设定判断，指出脸、发型、衣服、道具和画风偏差，不臆测缺失的参考图。'},
    'lighting': {'name': '灯光特效 AI', 'task': '统一光线方向、色调与特效设计', 'instruction': '你是灯光和特效设计师。让光源、色温、特效范围与剧情一致，禁止无依据的时间跳变和过度发光。'},
    'camera': {'name': '运镜 AI', 'task': '检查首帧动作衔接与可执行运镜', 'instruction': '你是摄影与运镜设计师。让动作从首帧状态延续，控制运动复杂度，不重复已经完成的动作。'},
    'supervisor': {'name': '总监管 AI', 'task': '审校剧情、资产引用、时长与连续性', 'instruction': '你是总监管。交叉核对原文、导演意图与剧本，修正冲突，明确仍需要人工审查的部分。'},
}


def config():
    return storage.get('workspace_items', ID) or {'id': ID, 'category': 'ai_team', 'version': 0, 'roles': {k: {'provider_id': '', 'vision': False, 'note': ''} for k in ROLES}}


def fingerprint(p):
    return hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='secret'}, sort_keys=True).encode()).hexdigest()


def validate_roles(roles):
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        raise ValueError('请配置完整的六个 AI 角色。')
    result = {}
    for key, value in roles.items():
        if not isinstance(value, dict):
            raise ValueError('角色配置无效。')
        identity = value.get('provider_id', '')
        note = value.get('note', '')
        if not isinstance(identity, str) or not isinstance(note, str) or len(note) > 1500:
            raise ValueError('角色连接或补充要求无效，要求最多1500字。')
        vision = value.get('vision') is True
        if identity:
            p = storage.get('providers', identity)
            if not p or p['kind'] != 'chat':
                raise ValueError(ROLES[key]['name']+'需要有效的文本模型连接。')
            if vision and p['protocol'] not in VISION_PROTOCOLS:
                raise ValueError('此协议尚未适配审图，请使用 Chat、Responses、Anthropic 或 Gemini。')
            if key == 'costume' and not vision:
                raise ValueError('定妆审图需确认所选模型支持图片输入，或留空改为人工审核。')
        result[key] = {'provider_id': identity, 'vision': vision, 'note': note.strip()}
    return result


def save(body):
    with storage.LOCK:
        old = config()
        if body.get('version') != old['version']:
            raise ValueError('AI 分工已在其他窗口更新，请刷新后保存。')
        value = {**old, 'version': old['version']+1, 'roles': validate_roles(body.get('roles')), 'updated_at': storage.now()}
        storage.put('workspace_items', value)
        return value


def snapshot(fallback, project_roles=None):
    roles = validate_roles(project_roles if project_roles is not None else config()['roles'])
    for key, value in roles.items():
        if not value['provider_id'] and key != 'costume':
            value['provider_id'] = fallback
            value['fallback'] = True
        if value['provider_id']:
            p = storage.get('providers', value['provider_id'])
            if not p or p['kind'] != 'chat':
                raise ValueError('项目备用文本连接无效。')
            value['signature'] = fingerprint(p)
            value['model'] = p['model']
    return copy.deepcopy(roles)


def resolve(project, role):
    binding = project.get('ai_team', {}).get(role)
    if not binding or not binding.get('provider_id'):
        return None
    p = storage.get('providers', binding['provider_id'])
    if not p or p['kind'] != 'chat' or binding['signature'] != fingerprint(p):
        raise ValueError(ROLES[role]['name']+'的模型连接已变化。请恢复该连接，或新建项目使用新配置。')
    return p


def references(value):
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError('最多添加8张原始稿图。')
    result = []
    for ref in value:
        if not isinstance(ref, dict) or ref.get('scope') not in ('style', 'asset'):
            raise ValueError('请选择画风参考或指定资产。')
        a = uploads.get(ref.get('upload_id'))
        target = ref.get('target', '')
        if not isinstance(target, str) or len(target) > 100 or ref['scope'] == 'asset' and not target.strip():
            raise ValueError('指定资产参考图需要填写对应人物或场景名称。')
        result.append({'upload_id': a['id'], 'scope': ref['scope'], 'target': target.strip()})
    return result


def matched(project, asset):
    names = [asset['name']] + str(asset.get('aliases', '')).replace('、', ',').split(',')
    return [r for r in project.get('references', []) if r['scope'] == 'style' or r['target'] in [n.strip() for n in names]]


def attach_vision(p, job, ids):
    if p['protocol'] not in VISION_PROTOCOLS:
        raise ValueError('该连接协议不支持审图。')
    if not 1 <= len(ids) <= 9:
        raise ValueError('审图需1–9张图片。')
    for identity in ids:
        uploads.get(identity)
    job['vision_upload_ids'] = list(dict.fromkeys(ids))


def add_vision_payload(p, job, body):
    ids = job.get('vision_upload_ids', [])
    if not ids:
        return body
    if p['kind'] != 'chat' or p['protocol'] not in VISION_PROTOCOLS:
        raise ValueError('当前模型协议不能接收审图图片。')
    protocol = p['protocol']
    if protocol == 'gemini':
        import base64
        parts = body['contents'][-1]['parts']
        for identity in ids:
            a, raw = uploads.binary(identity)
            parts.append({'inlineData': {'mimeType': a['mime'], 'data': base64.b64encode(raw).decode('ascii')}})
    else:
        key = 'input' if protocol == 'openai_responses' else 'messages'
        # Never mutate the durable plain-text message list during request building.
        body[key] = copy.deepcopy(body[key])
        m = body[key][-1]
        if protocol == 'openai_chat':
            m['content'] = [{'type': 'text', 'text': m['content']}] + [{'type': 'image_url', 'image_url': {'url': uploads.data_uri(i)}} for i in ids]
        elif protocol == 'openai_responses':
            m['content'] = [{'type': 'input_text', 'text': m['content']}] + [{'type': 'input_image', 'image_url': uploads.data_uri(i)} for i in ids]
        else:
            import base64
            m['content'] = [{'type': 'text', 'text': m['content']}]
            for identity in ids:
                a, raw = uploads.binary(identity)
                m['content'].append({'type': 'image', 'source': {'type': 'base64', 'media_type': a['mime'], 'data': base64.b64encode(raw).decode('ascii')}})
    return body


def dashboard():
    jobs = [storage.public_job(j) for j in storage.items('jobs', -1) if j.get('ai_role')]
    return {'config': config(), 'roles': ROLES, 'jobs': jobs[:80], 'usage': {
        k: {'requests': sum(j.get('ai_role') == k for j in jobs),
            'reported_tokens': sum((j.get('usage') or {}).get('total_tokens') or 0 for j in jobs if j.get('ai_role') == k),
            'unreported': sum(not (j.get('usage') or {}).get('total_tokens') for j in jobs if j.get('ai_role') == k)} for k in ROLES}}
