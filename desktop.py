"""Windowless portable entry point. Build this file with PyInstaller --windowed."""
import ctypes
import os
import sys
import traceback

import launcher


def install_logging(data):
    """PyInstaller --windowed sets stdio to None; keep errors in a writable log."""
    data.mkdir(parents=True, exist_ok=True)
    handle = None
    if sys.stdout is None or sys.stderr is None:
        handle = (data / 'service.log').open('a', encoding='utf-8', buffering=1)
        if sys.stdout is None:
            sys.stdout = handle
        if sys.stderr is None:
            sys.stderr = handle
    return handle


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    handle = None
    try:
        # Captured/inherited handles may use a non-Chinese Windows code page.
        # The launcher is imported here, so its __main__ stream setup does not run.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8', errors='backslashreplace')
        _, _, data = launcher.configuration()
        # Set this before importing storage/server, which resolve their paths once.
        os.environ['GUANGYU_DATA'] = str(data)
        handle = install_logging(data)
        if '--serve' in args:
            if set(args) - {'--serve', '--no-browser'}:
                raise RuntimeError('服务启动参数无效。')
            # A static import makes PyInstaller discover the entire server graph.
            import server
            return server.main()
        return launcher.main(args)
    except Exception as exc:
        if sys.stderr is not None:
            traceback.print_exc(file=sys.stderr)
        if os.name == 'nt' and '--no-browser' not in args:
            message = str(exc) + '\n\n如程序位于只读目录，请先解压到可写文件夹后启动。'
            ctypes.windll.user32.MessageBoxW(None, message, '光屿 AI · 启动失败', 0x10)
        return 1
    finally:
        if handle is not None:
            handle.flush()


if __name__ == '__main__':
    sys.exit(main())
