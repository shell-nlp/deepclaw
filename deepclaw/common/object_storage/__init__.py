from __future__ import annotations

from typing import Any

from deepclaw.common.object_storage.base import ObjectStorage
from deepclaw.common.object_storage.local import LocalObjectStorage
from deepclaw.common.object_storage.reader import ObjectStoragePDFReader
from deepclaw.constant import WORKSPACE_PATH


def create_object_storage(settings: Any) -> ObjectStorage:
    """根据配置创建本地或 MinIO 对象存储。

    Args:
        settings: 应用配置对象。

    Returns:
        对象存储实现。
    """
    provider = str(getattr(settings, "OBJECT_STORAGE_PROVIDER", "local")).strip().lower()
    if provider == "minio":
        endpoint_url = getattr(settings, "MINIO_ENDPOINT_URL", None)
        service_addresses = getattr(settings, "MINIO_SERVICE_ADDRESSES", None)
        endpoint_url = endpoint_url or (
            f"http://{service_addresses}" if service_addresses else None
        )
        access_key = getattr(settings, "MINIO_ACCESS_KEY", None)
        secret_key = getattr(settings, "MINIO_SECRET_KEY", None)
        if not all((endpoint_url, access_key, secret_key)):
            raise ValueError(
                "启用 MinIO 时必须配置 MINIO_ENDPOINT_URL、MINIO_ACCESS_KEY 和 MINIO_SECRET_KEY"
            )
        from deepclaw.common.object_storage.minio import MinioObjectStorage

        return MinioObjectStorage(
            endpoint_url=str(endpoint_url),
            access_key=str(access_key),
            secret_key=str(secret_key),
        )
    if provider != "local":
        raise ValueError("OBJECT_STORAGE_PROVIDER 只能是 local 或 minio")
    root_dir = getattr(settings, "LOCAL_STORAGE_ROOT", None)
    return LocalObjectStorage(root_dir or WORKSPACE_PATH / "pdf_files")


__all__ = [
    "LocalObjectStorage",
    "ObjectStorage",
    "ObjectStoragePDFReader",
    "create_object_storage",
]
