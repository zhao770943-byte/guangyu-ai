"""Explicit protocol capabilities and validation before any paid request."""
import math
import re
import copy

FLAGS = ('reference_images', 'first_frame', 'last_frame', 'negative_prompt', 'seed',
         'aspect_ratio', 'quality', 'batch', 'background', 'resolution', 'camera',
         'motion', 'strength', 'audio', 'voice', 'speed')
PARAMETERS = ('negative_prompt', 'seed', 'aspect_ratio', 'quality', 'n', 'background',
              'resolution', 'camera', 'motion', 'strength', 'audio', 'voice', 'speed')
VARIABLES = {flag: ('n' if flag == 'batch' else flag) for flag in FLAGS}


def template_variables(value):
    if isinstance(value, dict):
        return set().union(*(template_variables(v) for v in value.values()), set())
    if isinstance(value, list):
        return set().union(*(template_variables(v) for v in value), set())
    return set(re.findall(r'\{\{(.*?)\}\}', value)) if isinstance(value, str) else set()


def request_template(provider):
    """The effective template includes connection defaults overriding body fields."""
    def overlay(base, extra):
        result = copy.deepcopy(base)
        for key, value in extra.items():
            result[key] = overlay(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
        return result
    return overlay((provider.get('custom') or {}).get('body') or {}, provider.get('extra') or {})


def effective(provider):
    caps = dict.fromkeys(FLAGS, False)
    protocol, kind = provider.get('protocol'), provider.get('kind')
    model = provider.get('model', '').lower().removeprefix('models/')
    if protocol == 'custom':
        custom = provider.get('custom') or {}
        declared = custom.get('capabilities') or {}
        used = template_variables(request_template(provider))
        caps.update({k: declared.get(k) is True and VARIABLES[k] in used for k in FLAGS})
    elif kind == 'image' and protocol == 'openai_image':
        # Unknown compatible models need custom mappings; no model support is guessed.
        if model.startswith('gpt-image'):
            caps.update(reference_images=True, quality=True, batch=True, background=True)
        elif model == 'dall-e-2':
            caps.update(reference_images=True, batch=True)
        elif model == 'dall-e-3':
            caps.update(quality=True)
    elif kind == 'image' and protocol == 'gemini':
        caps['reference_images'] = True
        if 'image' in model:
            caps['aspect_ratio'] = True
            caps['resolution'] = model.startswith('gemini-3')
    elif kind == 'video' and protocol == 'openai_video':
        caps['first_frame'] = True
    elif kind == 'image' and protocol == 'minimax_image':
        caps.update(aspect_ratio=True,batch=True)
    elif kind == 'audio' and protocol in ('openai_speech','minimax_speech'):
        caps.update(voice=True,speed=True)
    return caps


def mapped_controls(provider):
    kind, protocol = provider.get('kind'), provider.get('protocol')
    if protocol == 'custom':
        used = template_variables(request_template(provider))
        return {'size': kind in ('image','video') and 'size' in used,
                'seconds': kind == 'video' and 'seconds' in used}
    return {'size': protocol in ('openai_image','openai_video'),
            'seconds': protocol == 'openai_video'}


def validate_custom(custom):
    declared = custom.get('capabilities', {})
    if not isinstance(declared, dict) or any(k not in FLAGS or type(v) is not bool for k, v in declared.items()):
        raise ValueError('自定义能力须为受支持能力名与布尔值组成的 JSON 对象。')
    used = template_variables(custom.get('body', {}))
    for flag, enabled in declared.items():
        if enabled and VARIABLES[flag] not in used:
            raise ValueError('已开启的能力必须在请求模板中引用：{{' + VARIABLES[flag] + '}}。')


def validate_job(provider, input_assets, parameters, size='auto'):
    import uploads
    if input_assets is None:
        input_assets = {}
    if parameters is None:
        parameters = {}
    if not isinstance(input_assets, dict) or set(input_assets) - {'references', 'first_frame', 'last_frame'}:
        raise ValueError('输入素材只支持参考图、首帧和尾帧。')
    if not isinstance(parameters, dict) or set(parameters) - set(PARAMETERS):
        raise ValueError('包含未知的高级参数。')
    caps = effective(provider)
    if provider.get('protocol')=='minimax_image' and size!='auto':
        raise ValueError('MiniMax 图像接口请使用画幅比例，尺寸保持自动。')
    if provider.get('protocol')=='gemini' and provider.get('kind')=='image' and size!='auto':
        raise ValueError('Gemini 图像接口不使用精确像素尺寸，请将尺寸设为自动，并使用宽高比和分辨率选项。请求尚未发送。')
    refs = input_assets.get('references', [])
    if not isinstance(refs, list) or len(refs) > 8:
        raise ValueError('最多选择 8 张参考图。')
    assets = {'references': refs, 'first_frame': input_assets.get('first_frame') or None,
              'last_frame': input_assets.get('last_frame') or None}
    if any(assets[k] is not None and not isinstance(assets[k],str) for k in ('first_frame','last_frame')):
        raise ValueError('首帧和尾帧应为上传图片 ID。')
    for field, flag in [('references', 'reference_images'), ('first_frame', 'first_frame'), ('last_frame', 'last_frame')]:
        value = assets[field]
        if value and not caps[flag]:
            raise ValueError('当前连接未声明支持此输入素材：' + flag + '。请更换模型或配置自定义协议。')
        for identity in value if isinstance(value, list) else ([value] if value else []):
            uploads.get(identity)
    clean = {}
    for key, value in parameters.items():
        if value is None or value == '':
            continue
        flag = 'batch' if key == 'n' else key
        if not caps[flag]:
            raise ValueError('当前连接不支持高级参数：' + key + '。请求尚未发送。')
        if key in ('seed', 'n'):
            maximum = 2147483647 if key == 'seed' else 10
            if type(value) is not int or not (0 if key == 'seed' else 1) <= value <= maximum:
                raise ValueError(key + ' 数值无效。')
        elif key == 'speed':
            lower,upper=(0.5,2) if provider.get('protocol')=='minimax_speech' else (0.25,4)
            if type(value) not in (int,float) or not math.isfinite(value) or not lower<=value<=upper:raise ValueError(f'语速需在 {lower}–{upper} 之间。')
        elif key == 'strength':
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('参考强度应为 0–1。')
        elif key == 'audio':
            if type(value) is not bool:
                raise ValueError('音频开关必须为布尔值。')
        else:
            if not isinstance(value, str) or len(value) > (4000 if key == 'negative_prompt' else 160):
                raise ValueError(key + ' 参数无效或过长。')
            if key == 'aspect_ratio' and not re.fullmatch(r'[1-9]\d?:[1-9]\d?', value):
                raise ValueError('宽高比格式应为 16:9 或 1:1。')
        clean[key] = value
    if provider.get('protocol')=='minimax_image':
        ratios=('1:1','16:9','4:3','3:2','2:3','3:4','9:16')+(() if provider.get('model')=='image-01-live' else ('21:9',))
        if clean.get('aspect_ratio','1:1') not in ratios or clean.get('n',1)>9:raise ValueError('MiniMax 图像宽高比或张数不受支持，张数最多 9。')
    if provider.get('protocol') == 'openai_image':
        model = provider.get('model', '').lower()
        qualities = ('standard', 'hd') if model == 'dall-e-3' else ('auto', 'low', 'medium', 'high')
        if model.startswith('gpt-image-2.5'):qualities += ('xhigh', 'max')
        if 'quality' in clean and clean['quality'] not in qualities:
            raise ValueError('图像质量选项不适用于当前模型。')
        if clean.get('background', 'auto') not in ('auto', 'transparent', 'opaque'):
            raise ValueError('背景选项应为 auto、transparent 或 opaque。')
        if model == 'dall-e-2' and len(refs) > 1:
            raise ValueError('DALL·E 2 仅支持一张参考图。')
        if model == 'dall-e-2' and refs:
            item=uploads.get(refs[0])
            if item['mime']!='image/png' or item['width']!=item['height'] or item['size']>=4*1024*1024:
                raise ValueError('DALL·E 2 参考图需为小于 4 MiB 的正方形 PNG。')
    if provider.get('protocol') == 'openai_video' and assets['first_frame']:
        item = uploads.get(assets['first_frame'])
        expected = size if size != 'auto' else provider.get('extra', {}).get('size', '720x1280')
        if expected != f"{item['width']}x{item['height']}":
            raise ValueError(f"首帧尺寸为 {item['width']}x{item['height']}，需与视频尺寸 {expected} 一致。请先调整图片或输出尺寸。")
    return assets, clean, caps
