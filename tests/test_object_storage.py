"""对象存储抽象与本地/MinIO 配置测试。"""

from types import SimpleNamespace

import pytest

from deepclaw.common.object_storage import (
    LocalObjectStorage,
    ObjectStoragePDFReader,
    create_object_storage,
)
from deepclaw.common.object_storage.minio import MinioObjectStorage


def test_local_object_storage_uses_bucket_and_file_path(tmp_path):
    """本地实现按 root/bucket/file_path 写入、读取和删除。"""
    storage = LocalObjectStorage(tmp_path)
    storage.put_bytes(
        "knowledge-bases",
        "user_1/kb_1/document.pdf",
        b"pdf-bytes",
        content_type="application/pdf",
    )

    assert (tmp_path / "knowledge-bases" / "user_1" / "kb_1" / "document.pdf").read_bytes() == b"pdf-bytes"
    assert storage.exists("knowledge-bases", "user_1/kb_1/document.pdf")
    assert storage.get_bytes("knowledge-bases", "user_1/kb_1/document.pdf") == b"pdf-bytes"

    storage.delete_object("knowledge-bases", "user_1/kb_1/document.pdf")
    assert not storage.exists("knowledge-bases", "user_1/kb_1/document.pdf")


def test_local_object_storage_rejects_path_escape(tmp_path):
    """本地实现拒绝越出根目录的对象路径。"""
    storage = LocalObjectStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.put_bytes("knowledge-bases", "../outside.pdf", b"bad")


def test_create_object_storage_defaults_to_local(tmp_path):
    """未显式选择 MinIO 时使用本地对象存储。"""
    storage = create_object_storage(
        SimpleNamespace(
            OBJECT_STORAGE_PROVIDER="local",
            LOCAL_STORAGE_ROOT=str(tmp_path),
        )
    )
    assert isinstance(storage, LocalObjectStorage)


def test_create_object_storage_requires_complete_minio_config():
    """启用 MinIO 时缺少连接参数应立即失败。"""
    with pytest.raises(ValueError):
        create_object_storage(
            SimpleNamespace(
                OBJECT_STORAGE_PROVIDER="minio",
                MINIO_ENDPOINT_URL="",
                MINIO_ACCESS_KEY="",
                MINIO_SECRET_KEY="",
                MINIO_SERVICE_ADDRESSES="",
            )
        )


def test_object_storage_implementations_inherit_base():
    """本地和 MinIO 实现都显式继承统一抽象。"""
    from deepclaw.common.object_storage.base import ObjectStorage

    assert issubclass(LocalObjectStorage, ObjectStorage)
    assert issubclass(MinioObjectStorage, ObjectStorage)


def test_object_storage_reader_loads_file_name_and_bytes(tmp_path):
    """文档读取器通过对象存储端口加载文件。"""
    storage = LocalObjectStorage(tmp_path)
    storage.put_bytes("knowledge-bases", "user_1/kb_1/document.pdf", b"content")
    loaded = ObjectStoragePDFReader(storage).load(
        "knowledge-bases", "user_1/kb_1/document.pdf"
    )
    assert loaded.file_name == "document.pdf"
    assert loaded.file_bytes == b"content"
