"""Local verified image inputs. Jobs store IDs, never inline image bodies."""
import base64
import binascii
import io
import json
import re
import warnings
import storage

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000


def save(body):
    encoded = body.get('data_base64')
    if not isinstance(encoded, str) or len(encoded) > ((MAX_BYTES + 2) // 3) * 4 + 100:
        raise ValueError('请上传不超过 10 MiB 的图片。')
    if encoded.startswith('data:'):
        match = re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,(.*)', encoded, re.S)
        if not match:
            raise ValueError('仅支持 PNG、JPEG、WebP 图片。')
        encoded = match[1]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError('图片 Base64 数据无效。') from None
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('图片为空或超过 10 MiB。')
    try:
        from PIL import Image
    except ImportError:
        raise ValueError('图片校验组件 Pillow 尚未安装；请使用安装了 Pillow 的 Python 启动。') from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as img:
                fmt, (width, height) = img.format, img.size
                if fmt not in ('PNG', 'JPEG', 'WEBP') or width * height > MAX_PIXELS:
                    raise ValueError('仅支持不超过 4000 万像素的 PNG、JPEG、WebP 图片。')
                if getattr(img, 'n_frames', 1) != 1:
                    raise ValueError('请使用静态图片，暂不支持动画图片。')
                img.verify()
            with Image.open(io.BytesIO(raw)) as img:
                img.load()  # Verify complete compressed data before persisting.
    except ValueError:
        raise
    except Exception:
        raise ValueError('图片无法完整解码，文件可能损坏或格式不受支持。') from None
    extension, mime = {'PNG': ('png', 'image/png'), 'JPEG': ('jpg', 'image/jpeg'), 'WEBP': ('webp', 'image/webp')}[fmt]
    identity = storage.uid()
    original = body.get('name', '参考图片')
    if not isinstance(original, str):
        raise ValueError('文件名无效。')
    name = re.sub(r'[\x00-\x1f\\/]', '_', original)[:180] or '参考图片'
    record = {'id': identity, 'url': '/uploads/' + identity + '.' + extension,
              'mime': mime, 'name': name, 'size': len(raw), 'width': width, 'height': height,
              'created_at': storage.now(), 'filename': identity + '.' + extension}
    directory = storage.DATA / 'uploads'
    directory.mkdir(exist_ok=True)
    temp = directory / (identity + '.partial')
    temp.write_bytes(raw)
    temp.replace(directory / record['filename'])
    (directory / (identity + '.json')).write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    return {k: v for k, v in record.items() if k != 'filename'}


def get(identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity):
        raise ValueError('输入图片 ID 无效，请重新选择图片。')
    directory = storage.DATA / 'uploads'
    try:
        record = json.loads((directory / (identity + '.json')).read_text(encoding='utf-8'))
        if not re.fullmatch(identity + r'\.(png|jpg|webp)', record.get('filename', '')):
            raise ValueError('图片记录无效。')
        if not (directory / record['filename']).is_file():
            raise ValueError('图片文件已不存在。')
        return record
    except (OSError, json.JSONDecodeError):
        raise ValueError('输入图片已不存在，请重新上传。') from None


def binary(identity):
    record = get(identity)
    return record, (storage.DATA / 'uploads' / record['filename']).read_bytes()


def data_uri(identity):
    record, raw = binary(identity)
    return 'data:' + record['mime'] + ';base64,' + base64.b64encode(raw).decode('ascii')
