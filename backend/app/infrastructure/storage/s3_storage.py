from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ValidationError
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
        s3_prefix = self._get_key(prefix.rstrip("/")) + "/" if prefix else ""
        paginator = self.client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    async def list_folders(self, prefix: str) -> list[str]:
        root = self._get_key(prefix.rstrip("/")) + "/"
        folders = set()
        for key in await self.list_keys(prefix):
            if not key.startswith(root):
                continue
            parts = key[len(root) :].split("/")[:-1]
            for length in range(1, len(parts) + 1):
                if parts[length - 1]:
                    folders.add(root + "/".join(parts[:length]))
        return sorted(folders)

    async def create_folder(self, key: str) -> None:
        # Explicit prefix marker preserves empty folders in object storage.
        if await self.exists(key):
            raise ConflictError("A file already exists at the folder path")
        self.client.put_object(Bucket=self.bucket, Key=self._get_key(key) + "/", Body=b"")

    async def delete_folder(self, key: str) -> bool:
        marker = self._get_key(key) + "/"
        keys = await self.list_keys(key)
        if any(item != marker for item in keys):
            raise ConflictError("Only empty folders can be deleted")
        self.client.delete_object(Bucket=self.bucket, Key=marker)
        return True

    async def move_folder(self, key: str, destination: str) -> None:
        source = self._get_key(key) + "/"
        target = self._get_key(destination) + "/"
        if target.startswith(source):
            raise ValidationError("Cannot move a folder inside itself")
        if await self.list_keys(destination) or await self.exists(destination):
            raise ConflictError("Destination already exists")
        keys = await self.list_keys(key)
        copies = []
        deleted = []
        try:
            for original in keys:
                copied = target + original[len(source) :]
                self.client.copy_object(
                    Bucket=self.bucket,
                    Key=copied,
                    CopySource={"Bucket": self.bucket, "Key": original},
                )
                copies.append((original, copied))
            for original, copied in copies:
                self.client.delete_object(Bucket=self.bucket, Key=original)
                deleted.append((original, copied))
        except BaseException:
            for original, copied in deleted:
                self.client.copy_object(
                    Bucket=self.bucket,
                    Key=original,
                    CopySource={"Bucket": self.bucket, "Key": copied},
                )
            for _, copied in copies:
                self.client.delete_object(Bucket=self.bucket, Key=copied)
            raise
