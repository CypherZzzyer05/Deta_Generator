"""Recover the final merge from existing shards; never start a solver.

Works with the already installed deta-generator 0.1.4/0.1.5. No package
upgrade or physical-source modification is required.
"""
import argparse
from contextlib import contextmanager
from dataclasses import replace
import functools
import json
from pathlib import Path
import sys
import time

import numpy as np

from deta_generator import merge, pipeline
from deta_generator.config import load_config


@contextmanager
def retry_merge_writes(attempts=201, delay=.1):
    """Cover both independently imported JSON-writer references in merge."""
    if attempts < 1 or delay < 0:
        raise ValueError('Invalid retry settings')
    stats = {'transient_write_retries': 0}
    original_json = pipeline.atomic_json
    original_merge_json = merge.atomic_json
    original_npz = pipeline.atomic_npz

    def wrap(writer):
        @functools.wraps(writer)
        def save(*args, **kwargs):
            for attempt in range(attempts):
                try:
                    return writer(*args, **kwargs)
                except PermissionError as error:
                    if (sys.platform != 'win32' or getattr(error, 'winerror', None) not in (5, 32, 33)
                            or attempt + 1 == attempts):
                        raise
                    stats['transient_write_retries'] += 1
                    if stats['transient_write_retries'] == 1:
                        print('Windows temporarily denied an output replacement; retrying for up to 20 seconds.', flush=True)
                    time.sleep(delay)
        return save
    pipeline.atomic_json = merge.atomic_json = wrap(original_json)
    pipeline.atomic_npz = wrap(original_npz)
    try:
        yield stats
    finally:
        pipeline.atomic_json = original_json
        merge.atomic_json = original_merge_json
        pipeline.atomic_npz = original_npz


def recover_merge(job_dir, output=None, attempts=201, delay=.1):
    root = Path(job_dir).resolve()
    config = load_config(root / 'job.json')
    layout = json.loads((root / 'parallel_plan.json').read_text(encoding='utf-8-sig'))
    count = layout.get('workers')
    if (isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 64
            or layout.get('samples') != config.sample_count):
        raise ValueError('Original task layout does not match job.json')
    directories = [root / f'shard{i}' for i in range(count)]
    missing = [str(p) for p in directories if not (p / 'manifest.json').is_file()]
    if missing:
        raise ValueError('Missing original shard manifests: ' + ', '.join(missing))
    # Preview only. The existing merger subsequently locks and fully verifies
    # every source file, geometry, material fit, solver version and mesh audit.
    successes = set()
    for index, directory in enumerate(directories):
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8-sig'))
        rows = {row['id']: row for row in manifest['samples']}
        for sample_id in range(index, config.sample_count, count):
            if rows.get(sample_id, {}).get('state') == 'success':
                successes.add(sample_id)
    if len(successes) != config.sample_count:
        remaining = sorted(set(range(config.sample_count)) - successes)
        raise ValueError(f'Only {len(successes)}/{config.sample_count} saved successes in original shards. '
                         f'No solver started. Missing/unfinished sample IDs: {remaining}')
    destination = Path(output).resolve() if output else root / 'merged_recovered'
    config = replace(config, output_dir=destination)
    print(f'Verifying and merging {config.sample_count} saved samples from {count} shards. No FDTD run.', flush=True)
    print('Output: ' + str(destination / 'dataset.npz'), flush=True)
    with retry_merge_writes(attempts, delay) as stats:
        summary = merge.merge_shards(config, directories)
    if summary['success'] != config.sample_count:
        raise ValueError('Merge is incomplete; original shards were preserved')
    with np.load(destination / 'dataset.npz', allow_pickle=False) as data:
        dimensions = len(config.parameter_names)
        if (data['spectra'].shape != (config.sample_count, 1000)
                or data['geometry_01'].shape != (config.sample_count, dimensions)
                or set(data['sample_ids'].tolist()) != set(range(config.sample_count))
                or not np.all(data['status'] == 2)):
            raise ValueError('Merged dataset failed final count/shape/ID/status checks')
    return {**summary, **stats, 'solver_run_performed': False,
            'original_shards_preserved': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='Default: a separate merged_recovered directory')
    args = parser.parse_args(argv)
    try:
        result = recover_merge(args.job_dir, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print('Merge interrupted. Original shards remain. Repeat the same command to recover.', file=sys.stderr)
        return 130
    except PermissionError as error:
        print(str(error), file=sys.stderr)
        print('Output is still inaccessible. Close file previews/readers and check the target file read-only '
              'attribute and directory write permissions. Original shards remain.', file=sys.stderr)
        return 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
