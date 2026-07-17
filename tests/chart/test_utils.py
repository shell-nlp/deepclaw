import os
import time

from deepclaw.middleware.chart.utils import cleanup_chart_files
from deepclaw.settings import settings


def test_cleanup_chart_files_removes_expired_and_excess_files(tmp_path, monkeypatch):
    """验证图表目录会清理过期文件并保留最新文件。

    Args:
        tmp_path: pytest 提供的临时目录。
        monkeypatch: pytest 提供的属性替换工具。
    """
    old_file = tmp_path / "old.png"
    middle_file = tmp_path / "middle.png"
    newest_file = tmp_path / "newest.png"
    for file_path in (old_file, middle_file, newest_file):
        file_path.write_bytes(b"png")

    now = time.time()
    os.utime(old_file, (now - 7_200, now - 7_200))
    os.utime(middle_file, (now - 20, now - 20))
    os.utime(newest_file, (now - 10, now - 10))
    monkeypatch.setattr(settings, "CHART_RETENTION_HOURS", 1)
    monkeypatch.setattr(settings, "CHART_MAX_FILES", 1)

    cleanup_chart_files(tmp_path)

    assert not old_file.exists()
    assert not middle_file.exists()
    assert newest_file.exists()
