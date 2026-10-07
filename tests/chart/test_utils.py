import time

from deepclaw.common.object_storage import LocalObjectStorage
from deepclaw.middleware.chart import storage as chart_storage
from deepclaw.settings import settings


def test_cleanup_chart_objects_removes_expired_and_excess_files(
    tmp_path, monkeypatch
):
    """验证图表对象存储会清理过期对象并保留最新对象。

    Args:
        tmp_path: pytest 提供的临时目录。
        monkeypatch: pytest 提供的属性替换工具。
    """
    object_storage = LocalObjectStorage(tmp_path)
    now = time.time()
    files = {
        "old": f"charts/{int(now - 7_200)}_0123456789abcdef0123456789abcdef.png",
        "middle": f"charts/{int(now - 20)}_0123456789abcdef0123456789abcdef.png",
        "newest": f"charts/{int(now - 10)}_0123456789abcdef0123456789abcdef.png",
    }
    for file_path in files.values():
        object_storage.put_bytes(
            chart_storage.CHART_BUCKET_NAME,
            file_path,
            b"png",
            content_type="image/png",
        )
    monkeypatch.setattr(settings, "CHART_RETENTION_HOURS", 1)
    monkeypatch.setattr(settings, "CHART_MAX_FILES", 1)

    chart_storage.cleanup_chart_objects(object_storage)

    assert not object_storage.exists(chart_storage.CHART_BUCKET_NAME, files["old"])
    assert not object_storage.exists(chart_storage.CHART_BUCKET_NAME, files["middle"])
    assert object_storage.exists(chart_storage.CHART_BUCKET_NAME, files["newest"])


def test_save_chart_png_uses_object_storage(tmp_path, monkeypatch):
    """验证图表 PNG 通过统一对象存储写入。"""
    object_storage = LocalObjectStorage(tmp_path)
    monkeypatch.setattr(
        chart_storage,
        "get_chart_object_storage",
        lambda: object_storage,
    )
    monkeypatch.setattr(settings, "CHART_MAX_FILES", 100)
    monkeypatch.setattr(settings, "CHART_RETENTION_HOURS", 24)

    file_name = chart_storage.save_chart_png(
        b"\x89PNG\r\n\x1a\n",
        created_at=time.time(),
    )

    object_key = f"{chart_storage.CHART_OBJECT_PREFIX}/{file_name}"
    assert object_storage.exists(chart_storage.CHART_BUCKET_NAME, object_key)
    assert (
        object_storage.get_bytes(chart_storage.CHART_BUCKET_NAME, object_key)
        == b"\x89PNG\r\n\x1a\n"
    )
