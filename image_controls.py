"""Image canvas presets shared by the UI and request validation."""
import math
import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _image_info(path, modified, size):
    from PIL import Image
    with Image.open(path) as image:
        return {'width':image.width, 'height':image.height, 'file_bytes':size}


def describe_asset(asset):
    """Read file headers without resampling or rewriting the original image."""
    if asset.get('type') != 'image' or not asset.get('local'):
        return asset
    try:
        import work_library
        path = work_library.local_path(asset.get('url'))
        stat = path.stat()
        return {**asset, **_image_info(str(path), stat.st_mtime_ns, stat.st_size)}
    except (OSError, ValueError):
        return asset

RATIOS = [('9:16', '抖音竖屏'), ('16:9', 'B站横屏'), ('1:1', '方形配图'),
          ('3:4', '小红书竖图'), ('4:3', '横向图文'), ('2:3', '人物海报'),
          ('3:2', '摄影横图'), ('4:5', '社交竖图'), ('5:4', '横向封面'),
          ('21:9', '电影宽屏'), ('9:21', '全屏壁纸'), ('2:1', '横幅'), ('1:2', '长海报')]


def flexible(model):
    return bool(re.match(r'^gpt-image-2(?:$|[.-])', model.lower()))


def dimensions(ratio, level):
    w, h = map(int, ratio.split(':'))
    divisor = math.gcd(w, h)
    w, h = w // divisor, h // divisor
    edge = (1024 if w == h else 1536) if level == 'standard' else 2048 if level == 'large' else 3840
    scale = min(edge // (16 * max(w, h)), math.isqrt(8294400 // (256 * w * h)))
    return f'{w * scale * 16}x{h * scale * 16}'


def options(provider):
    import capabilities
    protocol, model = provider.get('protocol'), provider.get('model', '').lower()
    caps = capabilities.effective(provider)
    result = {'mode': 'none', 'ratios': [], 'levels': [], 'quality': [], 'sizes': []}
    if provider.get('kind') != 'image':
        return result
    if caps['quality']:
        result['quality'] = [['standard', '标准'], ['hd', '高清']] if model == 'dall-e-3' else [
            ['low', '快速草稿'], ['medium', '均衡'], ['high', '精细']]
        if model.startswith('gpt-image-2.5'):
            result['quality'] += [['xhigh', 'xhigh · 平台扩展'], ['max', 'max · 平台扩展']]
    if protocol == 'openai_image' and flexible(model):
        result.update(mode='pixels', levels=[['standard', '标准'], ['large', '高清 · 长边约 2K'],
                                            ['ultra', '超清 · 最高约 8MP（实验性）']])
        result['ratios'] = [{'value': r, 'label': label, 'sizes': {level: dimensions(r, level)
                            for level in ('standard', 'large', 'ultra')}} for r, label in RATIOS]
    elif caps['aspect_ratio']:
        result['mode'] = 'aspect'
        ratios = dict(RATIOS)
        if protocol == 'minimax_image':
            allowed = ['1:1', '16:9', '4:3', '3:2', '2:3', '3:4', '9:16']
            if model != 'image-01-live':
                allowed.append('21:9')
        elif protocol == 'gemini':
            allowed = ['1:1', '3:4', '4:3', '2:3', '3:2', '4:5', '5:4', '9:16', '16:9', '21:9']
        else:
            allowed = list(ratios)
        result['ratios'] = [{'value': r, 'label': label} for r, label in RATIOS if r in allowed]
        if caps['resolution']:
            result['levels'] = [['1K', '1K'], ['2K', '2K'], ['4K', '4K']]
    elif capabilities.mapped_controls(provider)['size']:
        result['mode'] = 'fixed' if model.startswith('gpt-image-1') or model in ('dall-e-2', 'dall-e-3') else 'custom'
        result['sizes'] = ['1024x1024', '1536x1024', '1024x1536']
        if model == 'dall-e-2':
            result['sizes'] = ['256x256', '512x512', '1024x1024']
        elif model == 'dall-e-3':
            result['sizes'] = ['1024x1024', '1792x1024', '1024x1792']
    return result


def validate_size(provider, size):
    if size == 'auto' or provider.get('protocol') != 'openai_image':
        return
    model = provider.get('model', '').lower()
    if flexible(model):
        if not isinstance(size, str) or not re.fullmatch(r'\d+x\d+', size):
            raise ValueError('尺寸应为 宽x高，例如 864x1536。')
        w, h = map(int, size.split('x'))
        if not (w > 0 and h > 0 and w % 16 == h % 16 == 0 and max(w, h) <= 3840
                and max(w, h) <= 3 * min(w, h) and 655360 <= w * h <= 8294400):
            raise ValueError('当前模型尺寸要求：宽高为 16 的倍数，最长边不超过 3840，比例在 1:3–3:1，总像素为 655,360–8,294,400。请求尚未发送。')
    elif model.startswith('gpt-image-1') or model in ('dall-e-2', 'dall-e-3'):
        if size not in options(provider)['sizes']:
            raise ValueError('当前模型只支持这些尺寸：' + '、'.join(options(provider)['sizes']) + '。请更换画幅或模型。')
