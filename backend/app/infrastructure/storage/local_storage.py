import os
from pathlib import Path
from typing import Optional

import aiofiles

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.core.logging import log_operation
from app.core.paths import validate_relative_path
from app.infrastructure.storage.base import BaseStorage

settings = get_settings()


class LocalStorage(BaseStorage):
    def __init__(self, base_path: str | None = None):
        self.base_path = base_path or settings.LOCAL_STORAGE_PATH
        os.makedirs(self.base_path, exist_ok=True)

    def _get_full_path(self, key: str) -> str:
        validate_relative_path(key)
        base = Path(self.base_path).resolve()
        path = (base / key).resolve()
        if not path.is_relative_to(base):
            raise ValidationError("Storage path escapes the configured directory")
        return str(path)

    @log_operation("storage.save")
    async def save(self, key: str, content: bytes) -> str:
        full_path = self._get_full_path(key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)
        return key

    @log_operation("storage.get")
    async def get(self, key: str) -> Optional[bytes]:
        full_path = self._get_full_path(key)
        if not os.path.exists(full_path):
            return None
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    @log_operation("storage.delete")
    async def delete(self, key: str) -> bool:
        full_path = self._get_full_path(key)
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False

    @log_operation("storage.exists")
    async def exists(self, key: str) -> bool:
        full_path = self._get_full_path(key)
        return os.path.exists(full_path)

    @log_operation("storage.list_keys")
    async def list_keys(self, prefix: str) -> list[str]:
        full_prefix = (
            self._get_full_path(prefix.rstrip("/"))
            if prefix
            else str(Path(self.base_path).resolve())
        )
        keys = []
        for root, _, files in os.walk(full_prefix):
            for file in files:
                full_file = os.path.join(root, file)
                rel_path = os.path.relpath(full_file, self.base_path)
                keys.append(rel_path)
        return keys
