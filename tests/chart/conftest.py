import pytest

from deepclaw.common.object_storage import LocalObjectStorage
from deepclaw.middleware.chart import storage as chart_storage


@pytest.fixture(autouse=True)
def isolate_chart_object_storage(tmp_path, monkeypatch):
    """测试中将图表对象存储隔离到临时路径，避免污染生产目录。"""
    object_storage = LocalObjectStorage(tmp_path / "object_storage")
    monkeypatch.setattr(
        chart_storage,
        "get_chart_object_storage",
        lambda: object_storage,
    )
    yield
