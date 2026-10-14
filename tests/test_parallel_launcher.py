"""Windows launcher integration tests; simulated spectra are never research data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('powershell') or shutil.which('pwsh')


@unittest.skipUnless(sys.platform == 'win32' and POWERSHELL, 'Windows PowerShell integration')
class ParallelLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job = self.root/'job with spaces'
        site = self.root/'custom_site'
        site.mkdir()
        self.trace = self.root/'trace'
        self.trace.mkdir()
        # Each child uses the actual CLI, packing and merge implementations.
        # Only the native simulator is replaced by the existing test fixture.
        (site/'sitecustomize.py').write_text('''
import json, os, pathlib, sys, time
from test_generator import TestOnlySimulator
import deta_generator.pipeline as pipeline
import deta_generator.cli as cli
def test_native_check(config, preflight=False):
    # Test the entry sequencing, not native layout accuracy or FDTD physics.
    assert preflight and config.simulation.metal_mesh_nm == 8
    (pathlib.Path(os.environ['PARALLEL_TEST_TRACE']).parent/'preflight_called').write_text('test fixture only')
    return {'solver_run_performed':False,'test_fixture_only':True}
cli.native_check = test_native_check
class TimedTestSimulator(TestOnlySimulator):
    def __enter__(self):
        self.start = time.time()
        return self
    def __exit__(self, *args):
        trace = pathlib.Path(os.environ['PARALLEL_TEST_TRACE'])/f'{os.getpid()}.json'
        trace.write_text(json.dumps({'started':self.start,'ended':time.time()}))
    def run(self, geometry, project):
        if os.environ.get('PARALLEL_TEST_FAIL_SHARD') and '--shard-index' in sys.argv:
            index = sys.argv[sys.argv.index('--shard-index')+1]
            if index == os.environ['PARALLEL_TEST_FAIL_SHARD']:
                raise RuntimeError('Deliberate test-only shard failure')
        time.sleep(.02)
        return super().run(geometry, project)
pipeline.FDTDSimulator = TimedTestSimulator
''',encoding='utf-8')
        self.env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(site),str(ROOT/'src'),str(ROOT/'tests')]),
                        PARALLEL_TEST_TRACE=str(self.trace))

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, command, samples=100, env=None):
        return subprocess.run([POWERSHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/run-parallel.ps1'),
            '-Command',command,'-Python',sys.executable,'-JobDir',str(self.job),'-Samples',str(samples),
            '-Workers','4','-Concurrency','2','-Threads','1'],env=env or self.env,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=90)

    def test_prepare_100_then_parallel_run_merge_and_resume(self):
        prepared = self.invoke('prepare')
        self.assertEqual(prepared.returncode,0,prepared.stdout)
        self.assertFalse(list(self.trace.iterdir()))
        run = self.invoke('run')
        self.assertEqual(run.returncode,0,run.stdout)
        with np.load(self.job/'merged/dataset.npz') as data:
            self.assertEqual(data['spectra'].shape,(100,1000))
            self.assertEqual(data['geometry_values'].shape,(100,7))
            self.assertEqual(data['sample_ids'].tolist(),list(range(100)))
            self.assertEqual([len(data[name+'_indices']) for name in ('train','val','test')],[80,10,10])
        ids = []
        for index in range(4):
            manifest = json.loads((self.job/f'shard{index}/manifest.json').read_text())
            selected = [row['id'] for row in manifest['samples'] if row['state']=='success']
            self.assertEqual(selected,list(range(index,100,4)))
            ids += selected
        self.assertEqual(sorted(ids),list(range(100)))
        intervals = [json.loads(path.read_text()) for path in self.trace.iterdir()]
        self.assertEqual(len(intervals),4)
        events = sorted([(row['started'],1) for row in intervals]+[(row['ended'],-1) for row in intervals])
        active = peak = 0
        for _,change in events:
            active += change
            peak = max(peak,active)
        self.assertLessEqual(peak,2)
        with np.load(self.job/'merged/dataset.npz') as dataset:
            previous = {key:dataset[key].copy() for key in dataset.files if key!='metadata_json'}
        original_samples = {(index,path.name):path.read_bytes() for index in range(4)
                            for path in (self.job/f'shard{index}/samples').glob('*.npz')}
        resumed = self.invoke('run')
        self.assertEqual(resumed.returncode,0,resumed.stdout)
        self.assertEqual(len(list(self.trace.iterdir())),4)
        with np.load(self.job/'merged/dataset.npz') as dataset:
            for key,values in previous.items(): np.testing.assert_array_equal(dataset[key],values)
        for (index,name),original in original_samples.items():
            self.assertEqual((self.job/f'shard{index}/samples'/name).read_bytes(),original)

    def test_failed_worker_preserves_other_shards_then_can_resume(self):
        prepared = self.invoke('prepare',samples=8)
        self.assertEqual(prepared.returncode,0,prepared.stdout)
        failed = self.invoke('run',samples=8,env=dict(self.env,PARALLEL_TEST_FAIL_SHARD='1'))
        self.assertNotEqual(failed.returncode,0)
        self.assertFalse((self.job/'merged/dataset.npz').exists())
        self.assertTrue((self.job/'shard0/samples/sample_000000.npz').exists())
        resumed = self.invoke('run',samples=8)
        self.assertEqual(resumed.returncode,0,resumed.stdout)
        with np.load(self.job/'merged/dataset.npz') as data:
            self.assertEqual(data['sample_ids'].tolist(),list(range(8)))

    def test_existing_task_rejects_changed_sample_count(self):
        prepared = self.invoke('prepare',samples=8)
        self.assertEqual(prepared.returncode,0,prepared.stdout)
        original = (self.job/'job.json').read_bytes()
        changed = self.invoke('prepare',samples=100)
        self.assertNotEqual(changed.returncode,0)
        self.assertEqual((self.job/'job.json').read_bytes(),original)

    def test_pycharm_module_start_preflights_generates_and_merges(self):
        command = [sys.executable,'-m','deta_generator','parallel','--job-dir',str(self.job),
                   '--samples','8','--workers','4','--concurrency','2','--threads','1']
        result = subprocess.run(command,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                text=True,encoding='utf-8',errors='replace',timeout=90)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertTrue((self.root/'preflight_called').exists())
        self.assertIn('Starting CPU dataset generation',result.stdout)
        self.assertIn('success=8/8',result.stdout)
        with np.load(self.job/'merged/dataset.npz') as data:
            self.assertEqual(data['sample_ids'].tolist(),list(range(8)))
        status = subprocess.run(command+['--parallel-action','status'],env=self.env,stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=30)
        self.assertEqual(status.returncode,0,status.stdout)
        self.assertIn('success=8/8',status.stdout)


if __name__ == '__main__': unittest.main()
