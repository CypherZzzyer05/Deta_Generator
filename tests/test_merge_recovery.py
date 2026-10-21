"""Merge-only recovery from Windows read locks; spectra are test fixtures only."""
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from deta_generator import pipeline, merge
from deta_generator.cli import initialize
from deta_generator.config import load_config
from deta_generator.pipeline import atomic_json, checksum, directory_lock, generate_dataset, prepare_manifest
from test_generator import TestOnlySimulator

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/recover-merge.py'
spec = importlib.util.spec_from_file_location('merge_recovery', SCRIPT)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class MergeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.job = Path(self.temp.name) / 'job with spaces'
        initialize(self.job, 'au-metal', 4, 1, None, 8)
        self.config = load_config(self.job / 'job.json')
        atomic_json(self.job / 'parallel_plan.json', {'samples': 4, 'workers': 2})
        with patch('deta_generator.pipeline.FDTDSimulator', TestOnlySimulator):
            for shard in range(2):
                generate_dataset(replace(self.config, output_dir=self.job / f'shard{shard}'),
                                 sample_ids=range(shard, 4, 2))

    def tearDown(self):
        self.temp.cleanup()

    def hashes(self):
        return {str(p): checksum(p) for directory in self.job.glob('shard*')
                for p in directory.rglob('*') if p.is_file()}

    def test_merge_never_calls_solver_preserves_sources_and_is_repeatable(self):
        before = self.hashes()
        with patch('deta_generator.pipeline.FDTDSimulator', side_effect=AssertionError('No solver allowed')):
            first = recovery.recover_merge(self.job)
            second = recovery.recover_merge(self.job)
        self.assertEqual(first['success'], 4)
        self.assertEqual(second['success'], 4)
        self.assertFalse(first['solver_run_performed'])
        self.assertEqual(self.hashes(), before)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows destination read-handle regression')
    def test_real_windows_locked_manifest_retries_and_completes_merge(self):
        target = self.job / 'merged_recovered'
        target.mkdir()
        prepare_manifest(replace(self.config, output_dir=target))
        ready, release = threading.Event(), threading.Event()
        def reader():
            with (target / 'manifest.json').open('rb') as handle:
                handle.read()
                ready.set()
                release.wait(5)
        thread = threading.Thread(target=reader)
        thread.start()
        self.assertTrue(ready.wait(2))
        original = pipeline.atomic_json
        def write(path, data):
            try:
                return original(path, data)
            except PermissionError:
                release.set()
                raise
        try:
            with patch('deta_generator.pipeline.atomic_json', write):
                result = recovery.recover_merge(self.job, attempts=20, delay=.05)
            self.assertGreaterEqual(result['transient_write_retries'], 1)
            self.assertEqual(result['success'], 4)
        finally:
            release.set()
            thread.join(5)

    def test_permanent_permission_failure_is_bounded_and_writers_restored(self):
        denied = PermissionError('test permanent denial')
        denied.winerror = 5
        original_merge = merge.atomic_json
        with patch('deta_generator.pipeline.atomic_json', side_effect=denied) as write:
            with self.assertRaises(PermissionError):
                recovery.recover_merge(self.job, attempts=3, delay=0)
            self.assertEqual(write.call_count, 3)
        self.assertIs(merge.atomic_json, original_merge)

    def test_incomplete_shards_are_reported_without_launch_or_false_completion(self):
        path = self.job / 'shard1/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['samples'][3]['state'] = 'running'
        atomic_json(path, manifest)
        with self.assertRaisesRegex(ValueError, 'Only 3/4'):
            recovery.recover_merge(self.job)
        self.assertFalse((self.job / 'merged_recovered').exists())

    def test_corrupt_source_and_active_source_are_rejected(self):
        with directory_lock(self.job / 'shard0'):
            with self.assertRaisesRegex(RuntimeError, 'Another generator'):
                recovery.recover_merge(self.job)
        path = self.job / 'shard0/samples/sample_000000.npz'
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            recovery.recover_merge(self.job)
        self.assertEqual(path.read_bytes(), b'corrupt')

    def test_downloaded_script_runs_with_014_without_package_changes(self):
        previous = ROOT.parent / 'Deta_generator_parallel/src'
        if not previous.is_dir():
            self.skipTest('Historical local package unavailable')
        env = dict(os.environ, PYTHONPATH=str(previous))
        result = subprocess.run([sys.executable, str(SCRIPT), '--job-dir', str(self.job)],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"solver_run_performed": false', result.stdout)


if __name__ == '__main__':
    unittest.main()
