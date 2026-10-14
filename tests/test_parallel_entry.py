"""Packaged entry sequencing and compatibility; no native solver calls."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from deta_generator.cli import main
from deta_generator.parallel import run_parallel

ROOT = Path(__file__).resolve().parents[1]


class ParallelEntryTests(unittest.TestCase):
    def test_default_pycharm_dispatch_and_old_init_defaults(self):
        with patch('deta_generator.parallel.run_parallel',return_value=0) as launch:
            self.assertEqual(main(['parallel']),0)
            launch.assert_called_once_with(Path('jobs/au100_metal8_100'),100,4,None,16,None,'start',25)
        with patch('deta_generator.cli.initialize',return_value={}) as initialize:
            self.assertEqual(main(['init']),0)
            initialize.assert_called_once_with(Path('jobs/as2se3'),'au-metal',12,8,None,None)

    def test_packaged_script_matches_repository_controller(self):
        normalize = lambda path: path.read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(normalize(ROOT/'scripts/run-parallel.ps1'),
                         normalize(ROOT/'src/deta_generator/assets/scripts/run-parallel.ps1'))

    def test_failed_prepare_or_preflight_never_starts_workers(self):
        for codes,expected_count in (([1],1),([0,1],2)):
            with self.subTest(codes=codes), patch('deta_generator.parallel.sys.platform','win32'), \
                 patch('deta_generator.parallel.shutil.which',return_value='powershell'), \
                 patch('deta_generator.parallel.subprocess.run',side_effect=[SimpleNamespace(returncode=x) for x in codes]) as call:
                self.assertEqual(run_parallel('unused job with spaces'),1)
                self.assertEqual(call.call_count,expected_count)
                self.assertEqual(call.call_args_list[0].args[0][-1],'prepare')
                if expected_count == 2:
                    self.assertEqual(call.call_args_list[1].args[0][3],'preflight')

    def test_non_windows_is_rejected_before_launch(self):
        with patch('deta_generator.parallel.sys.platform','linux'), \
             patch('deta_generator.parallel.subprocess.run') as call:
            with self.assertRaisesRegex(ValueError,'Windows'):
                run_parallel('unused')
            call.assert_not_called()

    def test_api_override_reaches_preflight_and_packaged_controller(self):
        api = 'E:/API with spaces/lumapi.py'
        with patch('deta_generator.parallel.sys.platform','win32'), \
             patch('deta_generator.parallel.shutil.which',return_value='powershell'), \
             patch('deta_generator.parallel.subprocess.run',return_value=SimpleNamespace(returncode=0)) as call:
            self.assertEqual(run_parallel('unused',lumapi=api),0)
            self.assertEqual(call.call_count,3)
            for invocation in (call.call_args_list[0],call.call_args_list[2]):
                argv = invocation.args[0]
                self.assertEqual(argv[argv.index('-Lumapi')+1],api)
            argv = call.call_args_list[1].args[0]
            self.assertEqual(argv[argv.index('--lumapi')+1],api)

    def test_invalid_worker_plan_and_conflicting_physics_option_rejected(self):
        with patch('deta_generator.parallel.sys.platform','win32'), \
             patch('deta_generator.parallel.subprocess.run') as call:
            with self.assertRaises(ValueError):
                run_parallel('unused',samples=2,workers=4)
            self.assertEqual(main(['parallel','--metal-mesh-nm','4']),1)
            call.assert_not_called()


if __name__ == '__main__': unittest.main()
