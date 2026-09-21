from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend import app as app_module


@pytest.mark.parametrize(
    "configured_url",
    ["/deepclaw", "https://example.com/deepclaw"],
)
def test_register_charts_static_mounts_configured_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_url: str,
) -> None:
    """验证自定义图表前缀路径可以直接访问图表文件。

    Args:
        tmp_path: pytest 提供的临时目录。
        monkeypatch: pytest 提供的属性替换工具。
        configured_url: 待验证的 CHART_PUBLIC_URL 配置。
    """
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    (charts_dir / "sample.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(app_module, "workspace_path", tmp_path)
    monkeypatch.setattr(app_module.settings, "CHART_PUBLIC_URL", configured_url)

    app = FastAPI()
    app_module.register_charts_static(app)

    with TestClient(app) as client:
        response = client.get("/deepclaw/charts/sample.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
