from __future__ import annotations

import re
import time
import uuid

from loguru import logger

from deepclaw.common.object_storage import ObjectStorage, create_object_storage
from deepclaw.constant import WORKSPACE_PATH
from deepclaw.settings import settings

CHART_BUCKET_NAME = "chart-assets"
CHART_OBJECT_PREFIX = "charts"
_CHART_FILE_PATTERN = re.compile(r"(?P<created_at>\d+)_[0-9a-f]{32}\.png")
_LEGACY_CHART_FILE_PATTERN = re.compile(r"[0-9a-f]{32}\.png")
_chart_object_storage: ObjectStorage | None = None


def get_chart_object_storage() -> ObjectStorage:
    """获取图表对象存储单例。

    Returns:
        按当前配置创建或复用的对象存储实现。
    """
    global _chart_object_storage
    if _chart_object_storage is None:
        _chart_object_storage = create_object_storage(settings)
    return _chart_object_storage


def _is_valid_chart_file_name(file_name: str) -> bool:
    """判断图表文件名是否为允许的对象键名称。

    Args:
        file_name: 图表文件名。

    Returns:
        bool: 文件名合法时返回 True。
    """
    return bool(
        _CHART_FILE_PATTERN.fullmatch(file_name)
        or _LEGACY_CHART_FILE_PATTERN.fullmatch(file_name)
    )


def _chart_object_key(file_name: str) -> str:
    """把合法图表文件名转换为对象键。

    Args:
        file_name: 图表文件名。

    Returns:
        str: 图表对象键。

    Raises:
        ValueError: 文件名不符合图表资源命名规则时抛出。
    """
    if not _is_valid_chart_file_name(file_name):
        raise ValueError("图表文件名非法")
    return f"{CHART_OBJECT_PREFIX}/{file_name}"


def save_chart_png(data: bytes, *, created_at: float | None = None) -> str:
    """把 PNG 图表写入统一对象存储并执行保留策略。

    Args:
        data: PNG 文件字节。
        created_at: 图表创建时间，未传时使用当前时间。

    Returns:
        str: 可用于访问图表的文件名。
    """
    timestamp = int(created_at if created_at is not None else time.time())
    file_name = f"{timestamp}_{uuid.uuid4().hex}.png"
    object_storage = get_chart_object_storage()
    object_storage.put_bytes(
        CHART_BUCKET_NAME,
        _chart_object_key(file_name),
        data,
        content_type="image/png",
    )
    cleanup_chart_objects(object_storage)
    return file_name


def read_chart_png(file_name: str) -> bytes:
    """从对象存储读取图表 PNG，并兼容历史工作区文件。

    Args:
        file_name: 图表文件名。

    Returns:
        bytes: PNG 文件字节。
    """
    object_key = _chart_object_key(file_name)
    try:
        return get_chart_object_storage().get_bytes(CHART_BUCKET_NAME, object_key)
    except FileNotFoundError:
        legacy_path = WORKSPACE_PATH / "charts" / file_name
        if legacy_path.is_file():
            return legacy_path.read_bytes()
        raise


def cleanup_chart_objects(object_storage: ObjectStorage | None = None) -> None:
    """按保留时长和数量上限清理对象存储中的图表。

    Args:
        object_storage: 待清理的对象存储，未传时使用图表对象存储单例。
    """
    storage = object_storage or get_chart_object_storage()
    try:
        object_keys = storage.list_objects(
            CHART_BUCKET_NAME,
            f"{CHART_OBJECT_PREFIX}/",
        )
    except Exception as error:
        logger.warning("列出图表对象失败: error={}", repr(error))
        return

    now = time.time()
    retention_seconds = settings.CHART_RETENTION_HOURS * 3_600
    retained: list[tuple[int, str]] = []
    for object_key in object_keys:
        file_name = object_key.removeprefix(f"{CHART_OBJECT_PREFIX}/")
        match = _CHART_FILE_PATTERN.fullmatch(file_name)
        if match is None:
            continue
        created_at = int(match.group("created_at"))
        if now - created_at > retention_seconds:
            _delete_chart_object(storage, object_key)
            continue
        retained.append((created_at, object_key))

    retained.sort(key=lambda item: item[0], reverse=True)
    for _, object_key in retained[settings.CHART_MAX_FILES:]:
        _delete_chart_object(storage, object_key)


def _delete_chart_object(object_storage: ObjectStorage, object_key: str) -> None:
    """删除单个图表对象并记录失败日志。

    Args:
        object_storage: 图表对象存储。
        object_key: 待删除的对象键。
    """
    try:
        object_storage.delete_object(CHART_BUCKET_NAME, object_key)
    except Exception as error:
        logger.warning("删除图表对象失败: key={}, error={}", object_key, repr(error))
