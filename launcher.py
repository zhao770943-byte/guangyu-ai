"""Start and stop this local installation without touching unrelated processes."""
from pathlib import Path
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


def runtime_root():
    """Writable install directory, never PyInstaller's internal resource folder."""
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def data_directory():
    configured = Path(os.environ.get('GUANGYU_DATA', 'data')).expanduser()
    return (configured if configured.is_absolute() else runtime_root() / configured).resolve()


def instance_id(data):
    return hashlib.sha256(str(data.resolve()).casefold().encode('utf-8')).hexdigest()[:20]


def configuration():
    try:
        port = int(os.environ.get('GUANGYU_PORT', '8786'))
    except ValueError as exc:
        raise RuntimeError('GUANGYU_PORT 必须是 1–65535 之间的整数。') from exc
    if not 1 <= port <= 65535:
        raise RuntimeError('GUANGYU_PORT 必须是 1–65535 之间的整数。')
    return port, f'http://127.0.0.1:{port}', data_directory()


def local_opener():
    # Loopback control must not pass through HTTP_PROXY/HTTPS_PROXY on the host.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def read(opener, origin, path):
    with opener.open(origin + path, timeout=2) as response:
        return json.load(response)


def launch_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--serve', '--no-browser']
    return [sys.executable, str(runtime_root() / 'server.py')]


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    unknown = set(args) - {'--stop', '--no-browser', '--supervised'}
    if unknown:
        raise RuntimeError('不支持的启动参数：' + ', '.join(sorted(unknown)))
    port, origin, data = configuration()
    opener = local_opener()
    health = None
    try:
        health = read(opener, origin, '/api/health')
    except (OSError, ValueError):
        pass
    recognized = isinstance(health, dict) and health.get('app') == 'GuangyuAI'
    running = recognized and health.get('instance') == instance_id(data)
    if recognized and not running:
        raise RuntimeError(f'端口 {port} 已运行另一个版本或数据目录的光屿 AI。请先通过原程序安全停止它，或设置 GUANGYU_PORT 使用其他端口。')
    if '--stop' in args:
        if not running:
            data.mkdir(parents=True,exist_ok=True)
            (data/'service.paused').write_text('User requested stop\n',encoding='utf-8')
            print('此数据目录的光屿 AI 当前未运行。')
            return 0
        token = read(opener, origin, '/api/bootstrap')['csrf']
        request = urllib.request.Request(origin + '/api/shutdown', data=b'{}', headers={
            'Content-Type': 'application/json', 'Origin': origin, 'X-CSRF-Token': token,
        })
        try:
            with opener.open(request, timeout=5) as response:
                json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                reason = json.load(exc).get('error', '关闭失败。')
            except (ValueError, AttributeError):
                reason = '关闭失败，请检查服务日志。'
            raise RuntimeError(reason) from exc
        for _ in range(40):
            try:
                if read(opener, origin, '/api/health').get('instance') != instance_id(data):
                    break
            except (OSError, ValueError, AttributeError):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('已提交关闭请求，服务仍在退出，请稍后检查。')
        print('光屿 AI 已关闭。数据和密钥仍保存在本机。')
        return 0
    if '--supervised' in args:
        if (data/'service.paused').exists():return 0
    else:
        (data/'service.paused').unlink(missing_ok=True)
    if not running:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError(f'端口 {port} 被其他程序占用，未改动该程序。可设置 GUANGYU_PORT 后启动。')
        data.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment['GUANGYU_DATA'] = str(data)
        environment['GUANGYU_PORT'] = str(port)
        environment['PYTHONIOENCODING'] = 'utf-8'
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if os.name == 'nt' else 0
        with (data / 'service.log').open('a', encoding='utf-8') as log:
            process = subprocess.Popen(launch_command(), cwd=runtime_root(), env=environment,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=flags)
        for _ in range(120):
            try:
                ready = read(opener, origin, '/api/health')
                if ready.get('app') == 'GuangyuAI' and ready.get('instance') == instance_id(data):
                    break
            except (OSError, ValueError, AttributeError):
                pass
            if process.poll() is not None:
                raise RuntimeError(f'服务未能启动，请查看日志：{data / "service.log"}')
            time.sleep(.15)
        else:
            raise RuntimeError(f'服务启动超时，请查看日志：{data / "service.log"}')
    if '--no-browser' not in args:
        webbrowser.open(origin)
    print('光屿 AI 已运行：' + origin)
    print('关闭网页不会停止后台服务。需要停止时运行“停止光屿AI.cmd”。')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        sys.exit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
