import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.common.object_storage import LocalObjectStorage
from deepclaw.web_backend import app as app_module


@pytest.mark.parametrize(
    "configured_url",
    ["/deepclaw", "https://example.com/deepclaw"],
)
def test_register_charts_static_mounts_configured_prefix(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    configured_url: str,
) -> None:
    """验证自定义图表前缀路径可以直接访问图表文件。

    Args:
        tmp_path: pytest 提供的临时目录。
        monkeypatch: pytest 提供的属性替换工具。
        configured_url: 待验证的 CHART_PUBLIC_URL 配置。
    """
    object_storage = LocalObjectStorage(tmp_path / "objects")
    file_name = "1700000000_0123456789abcdef0123456789abcdef.png"
    object_storage.put_bytes(
        "chart-assets",
        f"charts/{file_name}",
        b"\x89PNG\r\n\x1a\n",
        content_type="image/png",
    )
    monkeypatch.setattr(
        app_module.chart_storage,
        "get_chart_object_storage",
        lambda: object_storage,
    )
    monkeypatch.setattr(app_module.settings, "CHART_PUBLIC_URL", configured_url)

    app = FastAPI()
    app_module.register_charts_static(app)

    with TestClient(app) as client:
        response = client.get(f"/deepclaw/charts/{file_name}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
