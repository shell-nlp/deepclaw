from __future__ import annotations

from pathlib import Path

from deepclaw.common.object_storage.base import ObjectStorage
from deepclaw.common.text_splitter import LoadedPDFFile


class ObjectStoragePDFReader:
    """把统一对象存储适配为文档解析器读取端口。"""

    def __init__(self, object_storage: ObjectStorage):
        """保存对象存储实现。

        Args:
            object_storage: 对象存储实现。
        """
        self.object_storage = object_storage

    def load(self, bucket_name: str, file_path: str) -> LoadedPDFFile:
        """从对象存储读取文件。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        return LoadedPDFFile(
            file_bytes=self.object_storage.get_bytes(bucket_name, file_path),
            file_name=Path(file_path).name,
        )
