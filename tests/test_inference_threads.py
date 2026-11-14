from pathlib import Path

import pytest

from src import quantized_classifier as classifier


@pytest.mark.parametrize('affinity,files,expected', [
    (16, {}, 4),
    (-1, {}, 4),
    (1, {'/sys/fs/cgroup/cpu.max': 'max 100000'}, 1),
    (16, {'/sys/fs/cgroup/cpu.max': '200000 100000'}, 2),
    (16, {'/sys/fs/cgroup/cpu.max': '150000 100000'}, 2),
    (16, {'/sys/fs/cgroup/cpu/cpu.cfs_quota_us': '100000',
          '/sys/fs/cgroup/cpu/cpu.cfs_period_us': '100000'}, 1),
    (16, {'/sys/fs/cgroup/cpu.max': 'invalid'}, 4),
])
def test_threads_respect_host_affinity_and_container_quota(monkeypatch, affinity, files, expected):
    monkeypatch.setattr(classifier.os, 'cpu_count', lambda: 32)
    def cpu_affinity(_):
        if affinity < 0:
            raise PermissionError('Affinity unavailable on this host')
        return set(range(affinity))

    monkeypatch.setattr(classifier.os, 'sched_getaffinity', cpu_affinity, raising=False)

    def read(path):
        key = path.as_posix()
        if key not in files:
            raise FileNotFoundError(key)
        return files[key]

    monkeypatch.setattr(Path, 'read_text', read)
    assert classifier._inference_threads() == expected
