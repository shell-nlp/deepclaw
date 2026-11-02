"""安装包发布状态与公开下载链路测试。"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend.devices import installer
from deepclaw.web_backend.devices.router import router


@pytest.fixture
def installer_client(tmp_path, monkeypatch):
    """挂载真实设备路由，隔离安装包且不启动数据库。

    Args:
        tmp_path: 临时发布目录。
        monkeypatch: 隔离发布路径。
    """
    monkeypatch.setattr(installer, "INSTALLER_PATH", tmp_path / installer.INSTALLER_NAME)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client


def test_installer_unpublished_and_empty(installer_client):
    """未发布和空文件均无下载入口，并返回可见中文错误。

    Args:
        installer_client: 隔离 HTTP 客户端。
    """
    for empty in (False, True):
        if empty:
            installer.INSTALLER_PATH.touch()
        response = installer_client.get("/api/devices/installer")
        assert response.json() == {"available": False, "size_bytes": None}
        assert response.headers["cache-control"] == "no-store"
        response = installer_client.get("/api/devices/installer/windows-x64")
        assert response.status_code == 404
        assert "暂未发布" in response.json()["detail"]


def test_installer_download_and_range_without_login(installer_client):
    """访客直接下载真实字节，浏览器接收附件且支持范围请求。

    Args:
        installer_client: 隔离 HTTP 客户端。
    """
    content = b"MZ-test-installer"
    installer.INSTALLER_PATH.write_bytes(content)
    assert installer_client.get("/api/devices/installer").json() == {
        "available": True, "size_bytes": len(content),
    }
    response = installer_client.get("/api/devices/installer/windows-x64")
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "application/octet-stream"
    assert f'attachment; filename="{installer.INSTALLER_NAME}"' == response.headers["content-disposition"]
    response = installer_client.get("/api/devices/installer/windows-x64", headers={"Range": "bytes=0-1"})
    assert response.status_code == 206
    assert response.content == b"MZ"


def test_update_manifest_and_versioned_files(installer_client):
    """公开更新清单和版本附件支持范围读取，禁止任意文件路径。

    Args:
        installer_client: 隔离 HTTP 客户端。
    """
    assert installer_client.get("/api/devices/updates/latest.yml").status_code == 404
    updates = installer.INSTALLER_PATH.parent / "updates"
    updates.mkdir()
    manifest = {"version": "0.1.2", "files": [{"url": "DeepClaw-Setup-x64-0.1.2.exe"}]}
    (updates / "latest.yml").write_text(json.dumps(manifest), encoding="utf-8")
    (updates / "DeepClaw-Setup-x64-0.1.2.exe").write_bytes(b"MZ-update")
    (updates / "DeepClaw-Setup-x64-0.1.2.exe.blockmap").write_bytes(b"blockmap")
    (updates / "credentials.json").write_bytes(b"private")
    response = installer_client.get("/api/devices/updates/latest.yml")
    assert response.json() == manifest
    assert response.headers["cache-control"] == "no-store"
    response = installer_client.get("/api/devices/updates/DeepClaw-Setup-x64-0.1.2.exe", headers={"Range": "bytes=0-1"})
    assert response.status_code == 206
    assert response.content == b"MZ"
    assert installer_client.get("/api/devices/updates/DeepClaw-Setup-x64-0.1.2.exe.blockmap").content == b"blockmap"
    assert installer_client.get("/api/devices/updates/credentials.json").status_code == 404
    assert installer_client.get("/api/devices/updates/DeepClaw-Setup-x64-0.1.3.exe").status_code == 404
