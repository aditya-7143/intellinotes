from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.logging import log_operation
from app.core.paths import validate_relative_path
from app.infrastructure.storage.base import BaseStorage

settings = get_settings()


class S3Storage(BaseStorage):
    def __init__(
        self,
        bucket: str | None = None,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
    ):
        self.bucket = bucket or settings.S3_BUCKET
        if not self.bucket:
            raise ValueError("S3_BUCKET not configured")

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or settings.S3_ENDPOINT_URL,
            aws_access_key_id=access_key or settings.S3_ACCESS_KEY,
            aws_secret_access_key=secret_key or settings.S3_SECRET_KEY,
            region_name=region or settings.S3_REGION,
        )

    def _get_key(self, key: str) -> str:
        return validate_relative_path(key)

    @log_operation("storage.save")
    async def save(self, key: str, content: bytes) -> str:
        s3_key = self._get_key(key)
        self.client.put_object(Bucket=self.bucket, Key=s3_key, Body=content)
        return key

    @log_operation("storage.get")
    async def get(self, key: str) -> Optional[bytes]:
        s3_key = self._get_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=s3_key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    @log_operation("storage.delete")
    async def delete(self, key: str) -> bool:
        s3_key = self._get_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError:
            return False

    @log_operation("storage.exists")
    async def exists(self, key: str) -> bool:
        s3_key = self._get_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    @log_operation("storage.list_keys")
    async def list_keys(self, prefix: str) -> list[str]:
        s3_prefix = self._get_key(prefix.rstrip("/")) if prefix else ""
        paginator = self.client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
