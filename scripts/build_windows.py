"""Build a Windows x64 portable release from an isolated build environment.

Run: python -m pip install -r requirements-build.txt
     python scripts/build_windows.py
No user data or repository working-directory files are copied implicitly.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
BUILD = ROOT / 'build'
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()


def dependency_license(package, target):
    distribution = importlib.metadata.distribution(package)
    files = [p for p in distribution.files or [] if '.dist-info/licenses/' in str(p).replace('\\', '/')]
    if not files:
        raise RuntimeError('Missing license files: ' + package)
    for item in files:
        relative = str(item).replace('\\', '/').split('/licenses/', 1)[1]
        path = target / package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(distribution.locate_file(item), path)


def build():
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise SystemExit('Build with 64-bit Python on Windows.')
    tag = os.environ.get('GITHUB_REF_NAME', '')
    if tag.startswith('v') and tag != 'v' + VERSION:
        raise SystemExit('Git tag and VERSION do not match.')
    DIST.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    # A code-drawn application mark consistent with the website's half-circle logo.
    from PIL import Image, ImageDraw
    icon = Image.new('RGBA', (256, 256), '#171c28')
    draw = ImageDraw.Draw(icon)
    draw.ellipse((44, 44, 212, 212), outline='#a6b0ff', width=8)
    draw.pieslice((44, 44, 212, 212), 0, 180, fill='#a6b0ff')
    icon_path = BUILD / 'guangyu.ico'
    icon.save(icon_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--windowed', '--name', 'GuangyuAI', '--icon', str(icon_path),
        '--distpath', str(DIST), '--workpath', str(BUILD / 'pyinstaller'),
        '--specpath', str(BUILD), '--add-data', str(ROOT / 'public') + os.pathsep + 'public',
        '--collect-all', 'av',
        '--paths', str(ROOT), str(ROOT / 'desktop.py'),
    ], cwd=ROOT, check=True)
    bundle = DIST / 'GuangyuAI'
    # Explicit distribution allowlist: only application files and public documentation.
    for name in ('LICENSE', 'README.md', '使用说明.md', '设计与接入方案.md', '验收记录.md',
                 'CHANGELOG.md', 'CONTRIBUTING.md', 'SECURITY.md', 'VERSION'):
        shutil.copy2(ROOT / name, bundle / name)
    for path in (ROOT / 'docs').rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.md', '.jpg', '.png'):
            target = bundle / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (bundle / '停止光屿AI.cmd').write_bytes(
        '@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\nstart "" /wait "%~dp0GuangyuAI.exe" --stop\r\n'.encode('utf-8'))
    (bundle / '开始使用.txt').write_text(
        '光屿 AI ' + VERSION + '\n\n'
        '1. 完整解压压缩包，保留 _internal 文件夹。\n'
        '2. 双击 GuangyuAI.exe，浏览器自动打开本机网页。无需安装 Python。\n'
        '3. 在模型接入中先选文本、音频、图像或视频，再选厂商，填写 Key 并一键获取对应型号。\n'
        '4. 关闭网页后服务继续运行；需要停止时双击 停止光屿AI.cmd。\n\n'
        '数据保存在程序旁的 data 文件夹，分享程序时不要分享 data。\n'
        '请解压到有写权限的普通文件夹，不要直接在压缩包中运行。\n'
        '本版本仅支持 Windows x64，程序没有代码签名。\n'
        '源码：https://github.com/zhao770943-byte/guangyu-ai\n', encoding='utf-8-sig')
    licenses = bundle / 'third-party-licenses'
    licenses.mkdir(exist_ok=True)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python license is missing.')
    shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    dependency_license('pillow', licenses)
    dependency_license('av', licenses)
    dependency_license('pyinstaller', licenses)
    (bundle / 'THIRD_PARTY_NOTICES.txt').write_text(
        'This bundle includes CPython, Pillow, PyAV (with FFmpeg libraries) and the PyInstaller bootloader.\n'
        'Their license terms are included in third-party-licenses/.\n'
        'The Pillow license bundle includes its third-party library notices.\n'
        'PyInstaller distribution exception applies to generated application bundles.\n'
        'Guangyu AI source code is licensed separately under the included MIT LICENSE.\n', encoding='utf-8')
    info = {'version': VERSION, 'platform': 'windows-x64', 'python': platform.python_version(),
            'pyinstaller': importlib.metadata.version('pyinstaller'),
            'pillow': importlib.metadata.version('pillow'),
            'av': importlib.metadata.version('av'),
            'built_at_utc': datetime.now(timezone.utc).isoformat(), 'code_signed': False}
    (bundle / 'build-info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    archive = DIST / ('GuangyuAI-v' + VERSION + '-windows-x64.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                relative = path.relative_to(bundle)
                if 'data' in relative.parts or path.suffix in ('.sqlite3', '.log'):
                    raise RuntimeError('Unexpected local state in bundle: ' + str(relative))
                output.write(path, Path('GuangyuAI') / relative)
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None:
            raise RuntimeError('ZIP verification failed.')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (DIST / 'SHA256SUMS.txt').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print(json.dumps({'archive': archive.name, 'bytes': archive.stat().st_size, 'sha256': digest}))


if __name__ == '__main__':
    build()
