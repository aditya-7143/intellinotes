from app.core.config import get_settings
from app.infrastructure.storage.base import BaseStorage
from app.infrastructure.storage.local_storage import LocalStorage
from app.infrastructure.storage.s3_storage import S3Storage

settings = get_settings()


def get_storage() -> BaseStorage:
    match settings.STORAGE_TYPE:
        case "local":
            return LocalStorage()
        case "s3":
            return S3Storage()
        case _:
            raise ValueError(f"Unknown storage type: {settings.STORAGE_TYPE}")
