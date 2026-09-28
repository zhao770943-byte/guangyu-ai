"""Bounded, read-only model discovery; no connection or generation is created.

Listing references:
https://developers.openai.com/api/reference/resources/models/methods/list
https://platform.claude.com/docs/en/api/models/list
https://ai.google.dev/api/models
"""
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import platform_catalog
import providers
import storage

MAX_RESPONSE = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_MODELS = 1000
MAX_PAGES = 10
TIMEOUT = 15
TOTAL_TIMEOUT = 45
KINDS = {'chat', 'image', 'video'}
PROTOCOLS = set().union(*providers.PROTOCOLS.values())
CAVEAT = '列表来自当前地址的只读模型接口；列出模型不代表已验证生成权限、余额或全部能力。用途按已适配模型系列提示，未知用途需确认用途与协议；专有接口可使用自定义 JSON 映射。'


def preset(identity):
    if not identity or identity == 'custom':
        return None
    item = platform_catalog.get_preset(identity)
    if not item:
        raise ValueError('平台预设不存在，请重新选择。')
    return item


def validate_platform(identity):
    if identity in ('', None):
        return 'custom'
    if not isinstance(identity, str) or len(identity) > 80:
        raise ValueError('平台标识无效。')
    preset(identity)
    return identity


def prepare(body):
    """Validate an unsaved form without requiring model ID or writing storage."""
    identity = body.get('id') or ''
    existing = None
    if identity:
        if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('连接 ID 无效。')
        existing = storage.get('providers', identity)
        if not existing:
            raise ValueError('连接已不存在，请刷新后重试。')
    old = existing or {}
    platform = validate_platform(body.get('platform', body.get('preset', old.get('platform', 'custom'))))
    selected = preset(platform) or {}
    platform_changed = bool(existing) and platform != old.get('platform', 'custom')
    kind = body.get('kind') or old.get('kind') or 'chat'
    if kind not in KINDS:
        raise ValueError('模型用途无效。')
    preferred_protocol = (selected.get('protocols') or {}).get(kind)
    protocol = body.get('protocol') or (preferred_protocol if platform_changed else old.get('protocol')) or preferred_protocol or 'openai_chat'
    if protocol not in PROTOCOLS:
        raise ValueError('模型列表协议无效。')
    allow_local = body.get('allow_local') is True
    if 'allow_local' not in body:
        allow_local = (selected.get('allow_local', False) if platform_changed else old.get('allow_local', selected.get('allow_local', False))) is True
    preferred_base = selected.get('base_url')
    base_url = body.get('base_url') or (preferred_base if platform_changed else old.get('base_url')) or preferred_base
    base_url = providers.validate_base_url(base_url, allow_local)
    key = body.get('api_key', '')
    if not isinstance(key, str) or len(key) > 8000 or any(ord(ch) < 32 for ch in key):
        raise ValueError('API Key 格式无效。')
    key = key.strip()
    secret = ''
    if key:
        secret = storage.crypt(key)
    elif old.get('secret'):
        if providers.canonical_base_url(old['base_url']) != providers.canonical_base_url(base_url):
            raise ValueError('接口地址已变更，请为新地址重新填写 API Key；不会将原连接密钥发送到新地址。')
        secret = old['secret']
    custom = body.get('custom', old.get('custom', {})) or {}
    if not isinstance(custom, dict):
        raise ValueError('自定义模型列表配置应为 JSON 对象。')
    path = providers.validate_discovery_path(body.get('discovery_path', custom.get('discovery_path')))
    header, prefix = providers.validate_custom_auth(custom)
    discovery_protocol = providers.validate_discovery_protocol(custom.get('discovery_protocol'))
    # The unsaved form's explicit protocol is this request's selection. An old
    # persisted directory protocol must not silently override it.
    if body.get('protocol'):
        discovery_protocol = ''
    return {'id': identity, 'platform': platform, 'kind': kind, 'protocol': protocol,
            'base_url': base_url, 'allow_local': allow_local, 'secret': secret,
            'custom': {'discovery_path': path, 'discovery_protocol': discovery_protocol,
                       'auth_header': header, 'auth_prefix': prefix}}


def _family(provider):
    # Listing is explicitly requested against the supplied destination. Preset
    # support metadata cannot decide whether a user's proxy exposes a catalog.
    protocol = provider['protocol']
    if protocol in ('anthropic', 'gemini'):
        return protocol
    return 'openai'


def _redact(text, key, limit=800):
    value = str(text)
    if key:
        for form in (key, urllib.parse.quote(key, safe=''), json.dumps(key)[1:-1]):
            value = value.replace(form, '[密钥已隐藏]')
    return re.sub(r'(?i)(bearer\s+)[^\s"<>]+', r'\1[已隐藏]', value)[:limit]


def _request(provider, path, key, timeout):
    request = urllib.request.Request(providers.endpoint(provider, path), headers=providers.headers(provider), method='GET')
    try:
        with providers.OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise providers.ProviderError('模型目录响应超过 4 MiB，已停止读取。请检查目录接口或在平台侧缩小目录范围后重试。')
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise providers.ProviderError('模型列表接口未返回 JSON，请核对 API 基础地址和列表路径。') from None
        if not isinstance(value, dict):
            raise providers.ProviderError('模型列表响应应为 JSON 对象。')
        if value.get('error'):
            raise providers.ProviderError('模型列表请求失败：' + _redact(json.dumps(value['error'], ensure_ascii=False), key))
        return value, len(raw)
    except urllib.error.HTTPError as ex:
        if 300 <= ex.code < 400:
            raise providers.ProviderError('模型列表接口返回重定向；为保护密钥未跟随。请填写最终 API 基础地址。') from None
        if ex.code in (404, 405, 501):
            raise providers.ProviderError(f'模型目录获取失败（HTTP {ex.code}）：当前地址未提供可读取的模型目录。请检查 API 基础地址、目录路径和平台权限后重试。') from None
        raw = ex.read(8000).decode('utf-8', errors='replace')
        detail = ''
        try:
            value = json.loads(raw)
            error = value.get('error', value.get('message', '')) if isinstance(value, dict) else ''
            detail = error.get('message', '') if isinstance(error, dict) else error
        except ValueError:
            pass
        raise providers.ProviderError(f'模型列表接口返回 HTTP {ex.code}：' + _redact(detail or '请检查地址、密钥与平台权限。', key)) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, OSError):
        raise providers.ProviderError('读取模型列表失败或超时，请检查网络和 API 地址。本次没有提交生成任务。') from None


def _suggestions(identity, item, family, provider):
    """Conservative protocol hints; never trust returned endpoint URLs."""
    model = identity.lower().removeprefix('models/')
    if family == 'anthropic':
        return ['chat'], 'anthropic'
    if family == 'gemini':
        methods = item.get('supportedGenerationMethods', [])
        if not isinstance(methods, list) or 'generateContent' not in methods:
            return [], None
        if model.startswith('gemini-') and 'image' in model:
            return ['image', 'chat'], 'gemini'
        return ['chat'], 'gemini'
    leaf = model.rsplit('/', 1)[-1]
    if leaf.startswith(('gpt-image-', 'chatgpt-image-', 'dall-e-')):
        return ['image'], 'openai_image'
    if leaf.startswith('sora-'):
        return ['video'], 'openai_video'
    if any(part in leaf for part in ('image', 'video', 'imagine', 'flux', 'sdxl', 'stable-diffusion', 'cogvideo')):
        return [], None
    if any(part in leaf for part in ('embedding', 'embed-', 'rerank', 'whisper', 'audio', 'realtime', 'transcrib', 'tts', 'moderation')):
        return [], None
    if leaf.startswith(('gpt-', 'chatgpt-', 'claude-', 'deepseek-', 'qwen', 'moonshot-', 'kimi-', 'grok-',
                        'glm-', 'minimax-', 'llama-', 'mistral-', 'gemini-')) or re.match(r'^o[1-9](?:-|$)', leaf):
        protocol = 'openai_responses' if provider['protocol'] == 'openai_responses' or 'codex' in leaf else 'openai_chat'
        return ['chat'], protocol
    return [], None


def _normalize(values, family, provider, key):
    if not isinstance(values, list):
        raise providers.ProviderError('平台返回的模型列表字段不是数组，请检查协议或自定义列表接口。')
    normalized, malformed = [], 0
    selected = preset(provider.get('platform')) or {}
    for item in values:
        if not isinstance(item, dict):
            malformed += 1
            continue
        identity = item.get('name') if family == 'gemini' else item.get('id', item.get('name'))
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 200 or any(ord(ch) < 32 for ch in identity):
            malformed += 1
            continue
        identity = identity.strip()
        if _redact(identity, key, 200) != identity:
            malformed += 1
            continue
        kinds, protocol = _suggestions(identity, item, family, provider)
        if provider['protocol'] == 'custom' and protocol:
            protocol = 'custom'
        elif selected:
            kinds = [kind for kind in kinds if kind in selected.get('protocols', {})]
            if not kinds:
                protocol = None
        label = item.get('display_name', item.get('displayName', item.get('name', identity)))
        label = label if isinstance(label, str) and label.strip() else identity
        entry = {'id': identity, 'name': _redact(label, key, 240), 'supported_kinds': kinds,
                 'protocol': protocol, 'base_url': provider['base_url']}
        if isinstance(item.get('description'), str):
            entry['description'] = _redact(item['description'], key, 600)
        normalized.append(entry)
    if values and not normalized:
        raise providers.ProviderError('模型列表没有有效的模型 ID，请核对返回格式。')
    return normalized, malformed


def _next_query(payload, family, values):
    if family == 'gemini':
        token = payload.get('nextPageToken')
        return ('pageToken', token) if token else None
    if payload.get('has_more') is True:
        cursor = payload.get('last_id')
        if not cursor and values:
            cursor = values[-1].get('id') if isinstance(values[-1], dict) else None
        if not cursor:
            raise providers.ProviderError('模型列表声明有下一页，但没有有效分页游标。')
        return ('after_id' if family == 'anthropic' else 'after', cursor)
    cursor = payload.get('next_cursor')
    return ('cursor', cursor) if cursor else None


def discover_saved(provider):
    """Discover from saved config, preserving providers/check's list-of-IDs API."""
    provider = dict(provider)
    provider['base_url'] = providers.validate_base_url(provider.get('base_url'), provider.get('allow_local'))
    custom = provider.get('custom') or {}
    discovery_protocol = providers.validate_discovery_protocol(custom.get('discovery_protocol'))
    catalog_provider = {**provider, 'protocol': discovery_protocol or provider['protocol']}
    providers.validate_custom_auth(custom)
    family = _family(catalog_provider)
    report = {'models': [], 'source': 'api', 'base_url': provider['base_url'],
              'protocol': provider['protocol'], 'pages': 0, 'truncated': False,
              'supported': True, 'caveat': CAVEAT}
    base_path = providers.validate_discovery_path((provider.get('custom') or {}).get('discovery_path')) or '/models'
    fixed_query = {'pageSize': 1000} if family == 'gemini' else ({'limit': 1000} if family == 'anthropic' else {})
    query = dict(fixed_query)
    key = storage.crypt(provider.get('secret', ''), decrypt=True)
    deadline, size = time.monotonic() + TOTAL_TIMEOUT, 0
    seen_ids, seen_cursors, malformed = set(), set(), 0
    for _ in range(MAX_PAGES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            report['truncated'] = True
            break
        path = base_path + ('?' + urllib.parse.urlencode(query) if query else '')
        payload, count = _request(catalog_provider, path, key, min(TIMEOUT, remaining))
        size += count
        if size > MAX_TOTAL_BYTES:
            report['truncated'] = True
            break
        values = payload.get('models') if family == 'gemini' else payload.get('data', payload.get('models', payload.get('items')))
        if values is None:
            raise providers.ProviderError('接口未返回 data/models/items 模型数组，请核对基础地址和协议。')
        entries, invalid = _normalize(values, family, provider, key)
        malformed += invalid
        report['pages'] += 1
        for entry in entries:
            if entry['id'] in seen_ids:
                continue
            if len(report['models']) >= MAX_MODELS:
                report['truncated'] = True
                break
            seen_ids.add(entry['id'])
            report['models'].append(entry)
        next_query = _next_query(payload, family, values)
        if not next_query:
            break
        name, cursor = next_query
        if not isinstance(cursor, str) or len(cursor) > 2048 or any(ord(ch) < 32 for ch in cursor):
            raise providers.ProviderError('模型列表分页游标无效。')
        if (name, cursor) in seen_cursors:
            raise providers.ProviderError('模型列表分页游标重复，已停止读取，避免无限请求。')
        seen_cursors.add((name, cursor))
        if len(report['models']) >= MAX_MODELS or report['pages'] >= MAX_PAGES:
            report['truncated'] = True
            break
        query = {**fixed_query, name: cursor}
    if malformed:
        report['caveat'] += f' 已忽略 {malformed} 条格式无效的模型记录。'
    if report['truncated']:
        report['caveat'] += ' 目录达到读取上限，当前仅展示已获取的部分模型。'
    return report


def discover(body):
    return discover_saved(prepare(body))
