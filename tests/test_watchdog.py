import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import launcher,watchdog

class WatchdogTests(unittest.TestCase):
    def test_pause_prevents_health_probe_and_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);(data/'service.paused').touch()
            with patch.object(launcher,'read') as read,patch.object(launcher,'main') as start:
                self.assertEqual(watchdog.ensure_service(None,'http://127.0.0.1:1',data),'paused')
                read.assert_not_called();start.assert_not_called()
    def test_healthy_instance_is_adopted_without_spawning(self):
        data=Path('fixture')
        with patch.object(launcher,'read',return_value={'app':'GuangyuAI','instance':launcher.instance_id(data)}),patch.object(launcher,'main') as start:
            self.assertEqual(watchdog.ensure_service(None,'http://127.0.0.1:1',data),'healthy');start.assert_not_called()
    def test_recovery_uses_guarded_launcher_and_propagates_conflicts(self):
        data=Path('fixture')
        with patch.object(launcher,'read',side_effect=OSError),patch.object(launcher,'main') as start:
            self.assertEqual(watchdog.ensure_service(None,'http://127.0.0.1:1',data),'recovered')
            start.assert_called_once_with(['--no-browser','--supervised'])
        with patch.object(launcher,'read',return_value={'app':'another-app'}),patch.object(launcher,'main',side_effect=RuntimeError('port occupied')):
            with self.assertRaisesRegex(RuntimeError,'occupied'):watchdog.ensure_service(None,'http://127.0.0.1:1',data)
    def test_manual_start_resumes_but_supervised_start_respects_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);marker=data/'service.paused';marker.touch()
            health={'app':'GuangyuAI','instance':launcher.instance_id(data)}
            with patch.object(launcher,'configuration',return_value=(1,'http://127.0.0.1:1',data)),patch.object(launcher,'read',return_value=health),patch.object(launcher.subprocess,'Popen') as spawn:
                launcher.main(['--no-browser','--supervised']);self.assertTrue(marker.exists())
                launcher.main(['--no-browser']);self.assertFalse(marker.exists());spawn.assert_not_called()

if __name__=='__main__':unittest.main()
