from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import PurePosixPath


class ObjectStorage(ABC):
    """对象存储抽象基类，隔离本地文件系统与 MinIO/S3。"""

    @abstractmethod
    def get_bytes(self, bucket_name: str, file_path: str) -> bytes:
        """读取对象字节。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        ...

    @abstractmethod
    def put_bytes(
        self,
        bucket_name: str,
        file_path: str,
        data: bytes,
        content_type: str | None = None,
    ) -> None:
        """写入对象字节。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
            data: 文件字节。
            content_type: 文件 MIME 类型。
        """
        ...

    @abstractmethod
    def exists(self, bucket_name: str, file_path: str) -> bool:
        """判断对象是否存在。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        ...

    @abstractmethod
    def delete_object(self, bucket_name: str, file_path: str) -> None:
        """删除对象，不存在时应保持幂等。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        ...


def normalize_object_location(bucket_name: str, file_path: str) -> tuple[str, str]:
    """校验并规范化对象地址。

    Args:
        bucket_name: 存储桶名称。
        file_path: 桶内文件路径。

    Returns:
        规范化后的存储桶名称和正斜杠路径。
    """
    normalized_bucket = bucket_name.strip()
    normalized_path = file_path.strip()
    if not normalized_bucket or normalized_bucket in {".", ".."}:
        raise ValueError("bucket_name 不能为空或使用相对路径标记")
    if any(separator in normalized_bucket for separator in ("/", "\\")):
        raise ValueError("bucket_name 不能包含路径分隔符")
    if not normalized_path or "\\" in normalized_path:
        raise ValueError("file_path 不能为空且必须使用正斜杠")

    key_path = PurePosixPath(normalized_path)
    if key_path.is_absolute() or any(
        part in {"", ".", ".."} for part in key_path.parts
    ):
        raise ValueError("file_path 必须是桶内的安全相对路径")
    if any(
        re.search(r'[<>:"|?*\x00-\x1f]', part) for part in key_path.parts
    ):
        raise ValueError("file_path 包含对象存储或本地文件系统不支持的字符")
    return normalized_bucket, key_path.as_posix()
