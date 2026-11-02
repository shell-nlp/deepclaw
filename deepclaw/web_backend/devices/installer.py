"""本机助手安装包与更新清单的受控分发入口。"""

import re

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from deepclaw.constant import HOME_PATH

INSTALLER_NAME = "DeepClaw-Setup-x64.exe"
INSTALLER_PATH = HOME_PATH / "downloads" / INSTALLER_NAME
router = APIRouter()


class DeviceInstallerResponse(BaseModel):
    """当前 Windows 安装包的发布状态。"""

    available: bool
    size_bytes: int | None = None


@router.get("/installer", response_model=DeviceInstallerResponse)
async def installer_status(response: Response):
    """查询安装包是否发布，不读取用户数据。

    Args:
        response: 用于禁止缓存发布状态的 HTTP 响应。
    """
    response.headers["Cache-Control"] = "no-store"
    try:
        size = INSTALLER_PATH.stat().st_size if INSTALLER_PATH.is_file() else 0
    except OSError:
        size = 0
    return DeviceInstallerResponse(available=size > 0, size_bytes=size or None)


@router.get("/installer/windows-x64")
async def download_installer():
    """下载固定发布目录中的 Windows 安装包，不接受外部路径。

    Args:
        无。
    """
    try:
        if INSTALLER_PATH.is_file() and INSTALLER_PATH.stat().st_size > 0:
            return FileResponse(INSTALLER_PATH, filename=INSTALLER_NAME,
                                media_type="application/octet-stream",
                                headers={"Cache-Control": "no-cache"})
    except OSError:
        pass
    raise HTTPException(404, "本机助手安装包暂未发布，请联系管理员。")


@router.get("/updates/latest.yml")
async def update_manifest():
    """分发最新版本清单，不允许缓存过期发布状态。

    Args:
        无。
    """
    path = INSTALLER_PATH.parent / "updates" / "latest.yml"
    if not path.is_file():
        raise HTTPException(404, "本机助手更新清单暂未发布。")
    return FileResponse(path, media_type="application/yaml", headers={"Cache-Control": "no-store"})


@router.get("/updates/{file_name}")
async def update_artifact(file_name: str):
    """仅分发符合固定命名规则的 Windows 更新包与差分映射。

    Args:
        file_name: 无目录的版本文件名。
    """
    if not re.fullmatch(r"DeepClaw-Setup-x64-\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\.exe(?:\.blockmap)?", file_name):
        raise HTTPException(404, "更新文件不存在。")
    path = INSTALLER_PATH.parent / "updates" / file_name
    if not path.is_file():
        raise HTTPException(404, "更新文件不存在。")
    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-cache"})
