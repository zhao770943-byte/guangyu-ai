"""Portable launcher contracts without starting a process or using user data."""
import os
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher
import desktop


class DesktopTests(unittest.TestCase):
    def test_source_default_is_independent_of_cwd(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(launcher.data_directory(), Path(launcher.__file__).resolve().parent / 'data')

    def test_frozen_data_adjacent_executable_not_meipass(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'GuangyuAI.exe'
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(exe)), patch.dict(os.environ, {}, clear=True):
                # Windows runners may expose TEMP with an 8.3 short-path alias.
                self.assertEqual(launcher.data_directory(), (Path(directory) / 'data').resolve())
                self.assertEqual(launcher.launch_command(), [str(exe), '--serve', '--no-browser'])

    def test_explicit_data_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GUANGYU_DATA': directory}):
            self.assertEqual(launcher.data_directory(), Path(directory).resolve())

    def test_relative_data_directory_relative_to_install(self):
        with patch.dict(os.environ, {'GUANGYU_DATA': 'portable-data'}):
            self.assertEqual(launcher.data_directory(), launcher.runtime_root() / 'portable-data')

    def test_port_validation(self):
        for value in ['abc', '0', '-1', '65536']:
            with self.subTest(value=value), patch.dict(os.environ, {'GUANGYU_PORT': value}):
                with self.assertRaisesRegex(RuntimeError, 'GUANGYU_PORT'):
                    launcher.configuration()

    def test_instance_differentiates_data_directories(self):
        self.assertEqual(launcher.instance_id(Path('data')), launcher.instance_id(Path('data')))
        self.assertNotEqual(launcher.instance_id(Path('data')), launcher.instance_id(Path('other-data')))

    def test_unknown_option_rejected_without_network(self):
        with self.assertRaisesRegex(RuntimeError, '启动参数'):
            launcher.main(['--invalid'])

    def test_captured_non_chinese_streams_use_utf8(self):
        stdout_bytes, stderr_bytes = io.BytesIO(), io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding='cp1252')
        stderr = io.TextIOWrapper(stderr_bytes, encoding='cp1252')

        def successful_launcher(args):
            self.assertEqual(args, ['--no-browser'])
            print('光屿 AI 已运行。')
            print('中文日志：启动成功。', file=sys.stderr)
            return 0

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'GUANGYU_DATA': directory}), \
                    patch.object(sys, 'stdout', stdout), patch.object(sys, 'stderr', stderr), \
                    patch.object(launcher, 'main', side_effect=successful_launcher):
                result = desktop.main(['--no-browser'])
            stdout.flush()
            stderr.flush()
            self.assertEqual(result, 0)
            self.assertIn('光屿 AI 已运行。', stdout_bytes.getvalue().decode('utf-8'))
            self.assertIn('中文日志：启动成功。', stderr_bytes.getvalue().decode('utf-8'))
        stdout.close()
        stderr.close()


if __name__ == '__main__':
    unittest.main()
