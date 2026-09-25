from __future__ import annotations

from typing import Any

from deepclaw.common.object_storage.base import (
    ObjectStorage,
    normalize_object_location,
)


class MinioObjectStorage(ObjectStorage):
    """基于 S3 兼容协议的 MinIO 对象存储实现。"""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
    ):
        """使用显式配置初始化 MinIO 客户端。

        Args:
            endpoint_url: MinIO/S3 服务地址。
            access_key: 访问密钥。
            secret_key: 私密密钥。
        """
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "使用 MinIO 对象存储需要安装 boto3，请执行 `uv sync --extra object-storage`。"
            ) from exc

        self._client_error = ClientError
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=boto3.session.Config(signature_version="s3v4"),
            verify=False,
        )

    def get_bytes(self, bucket_name: str, file_path: str) -> bytes:
        """读取 MinIO 对象字节。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        bucket_name, file_path = normalize_object_location(bucket_name, file_path)
        response = self.client.get_object(Bucket=bucket_name, Key=file_path)
        return response["Body"].read()

    def put_bytes(
        self,
        bucket_name: str,
        file_path: str,
        data: bytes,
        content_type: str | None = None,
    ) -> None:
        """写入 MinIO 对象，并在存储桶不存在时自动创建。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
            data: 文件字节。
            content_type: 文件 MIME 类型。
        """
        bucket_name, file_path = normalize_object_location(bucket_name, file_path)
        self._ensure_bucket(bucket_name)
        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        try:
            self.client.put_object(
                Bucket=bucket_name,
                Key=file_path,
                Body=data,
                IfNoneMatch="*",
                **extra_args,
            )
        except self._client_error as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {
                "409",
                "412",
                "ConditionalRequestConflict",
                "PreconditionFailed",
            }:
                raise FileExistsError(
                    f"对象已存在: {bucket_name}/{file_path}"
                ) from exc
            raise

    def exists(self, bucket_name: str, file_path: str) -> bool:
        """判断 MinIO 对象是否存在。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        bucket_name, file_path = normalize_object_location(bucket_name, file_path)
        try:
            self.client.head_object(Bucket=bucket_name, Key=file_path)
            return True
        except self._client_error as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete_object(self, bucket_name: str, file_path: str) -> None:
        """删除 MinIO 对象。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        bucket_name, file_path = normalize_object_location(bucket_name, file_path)
        self.client.delete_object(Bucket=bucket_name, Key=file_path)

    def _ensure_bucket(self, bucket_name: str) -> None:
        """确保目标存储桶存在。

        Args:
            bucket_name: 存储桶名称。
        """
        try:
            self.client.head_bucket(Bucket=bucket_name)
        except self._client_error as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.client.create_bucket(Bucket=bucket_name)
