from __future__ import annotations

import os
from pathlib import Path

from deepclaw.common.object_storage.base import (
    ObjectStorage,
    normalize_object_location,
    normalize_object_prefix,
)


class LocalObjectStorage(ObjectStorage):
    """使用本地目录模拟 bucket_name/file_path 对象存储。"""

    def __init__(self, root_dir: str | Path):
        """初始化本地对象存储根目录。

        Args:
            root_dir: 本地对象存储根目录。
        """
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def get_bytes(self, bucket_name: str, file_path: str) -> bytes:
        """读取本地对象字节。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        return self._resolve_path(bucket_name, file_path).read_bytes()

    def put_bytes(
        self,
        bucket_name: str,
        file_path: str,
        data: bytes,
        content_type: str | None = None,
    ) -> None:
        """以不覆盖方式写入本地对象。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
            data: 文件字节。
            content_type: 文件 MIME 类型，本地实现仅接收不落盘。
        """
        del content_type
        target = self._resolve_path(bucket_name, file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as file_handle:
                file_handle.write(data)
                file_handle.flush()
                os.fsync(file_handle.fileno())
        except FileExistsError as exc:
            raise FileExistsError(
                f"对象已存在: {bucket_name}/{file_path}"
            ) from exc
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def exists(self, bucket_name: str, file_path: str) -> bool:
        """判断本地对象是否存在。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        return self._resolve_path(bucket_name, file_path).is_file()

    def delete_object(self, bucket_name: str, file_path: str) -> None:
        """删除本地对象并清理空目录。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        target = self._resolve_path(bucket_name, file_path)
        target.unlink(missing_ok=True)
        parent = target.parent
        while parent != self.root_dir:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def list_objects(self, bucket_name: str, prefix: str = "") -> list[str]:
        """按前缀列出本地对象键。

        Args:
            bucket_name: 存储桶名称。
            prefix: 桶内对象键前缀。

        Returns:
            list[str]: 按对象键排序后的完整对象键列表。
        """
        bucket_name, prefix = normalize_object_prefix(bucket_name, prefix)
        bucket_dir = (self.root_dir / bucket_name).resolve()
        base_dir = (
            (bucket_dir / Path(*prefix.split("/"))).resolve()
            if prefix
            else bucket_dir
        )
        if self.root_dir not in base_dir.parents and base_dir != self.root_dir:
            raise ValueError("对象前缀超出本地存储根目录")
        if not base_dir.is_dir():
            return []

        object_keys: list[str] = []
        for file_path in base_dir.rglob("*"):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(base_dir).as_posix()
            object_keys.append(f"{prefix}/{relative_path}" if prefix else relative_path)
        return sorted(object_keys)

    def _resolve_path(self, bucket_name: str, file_path: str) -> Path:
        """把对象地址解析为受根目录约束的本地路径。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        bucket_name, file_path = normalize_object_location(bucket_name, file_path)
        target = (
            self.root_dir / bucket_name / Path(*file_path.split("/"))
        ).resolve()
        if self.root_dir not in target.parents:
            raise ValueError("对象路径超出本地存储根目录")
        return target
