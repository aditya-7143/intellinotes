import os
import tempfile
from pathlib import Path
from typing import Optional

import aiofiles

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
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
        candidate = base
        for part in key.split("/"):
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValidationError("Symlinked storage paths are not supported")
        path = (base / key).resolve()
        if not path.is_relative_to(base):
            raise ValidationError("Storage path escapes the configured directory")
        return str(path)

    @log_operation("storage.save")
    async def save(self, key: str, content: bytes) -> str:
        full_path = self._get_full_path(key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        # Readers must see a complete old or new file, never a partially written note.
        descriptor, temporary = tempfile.mkstemp(dir=os.path.dirname(full_path), prefix=".note-")
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, full_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
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

    async def list_folders(self, prefix: str) -> list[str]:
        root = Path(self._get_full_path(prefix))
        if not root.is_dir():
            return []
        directories = []
        for current, names, _ in os.walk(root, followlinks=False):
            # Never expose another user's tree through symlinked directories.
            names[:] = [name for name in names if not (Path(current) / name).is_symlink()]
            for name in names:
                relative = (Path(current) / name).relative_to(root).as_posix()
                directories.append(prefix.rstrip("/") + "/" + relative)
        return sorted(directories)

    async def create_folder(self, key: str) -> None:
        try:
            Path(self._get_full_path(key)).mkdir(parents=True, exist_ok=True)
        except FileExistsError as error:
            raise ConflictError("A file already exists at the folder path") from error

    async def move_folder(self, key: str, destination: str) -> None:
        source, target = Path(self._get_full_path(key)), Path(self._get_full_path(destination))
        if not source.is_dir():
            raise NotFoundError("Folder not found")
        if target.exists():
            raise ConflictError("Destination already exists")
        if target == source or target.is_relative_to(source):
            raise ValidationError("Cannot move a folder inside itself")
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)

    async def delete_folder(self, key: str) -> bool:
        folder = Path(self._get_full_path(key))
        if not folder.is_dir():
            return False
        try:
            folder.rmdir()
        except OSError as error:
            raise ConflictError("Only empty folders can be deleted") from error
        return True
