from abc import ABC, abstractmethod
from typing import Optional


class BaseStorage(ABC):
    @abstractmethod
    async def save(self, key: str, content: bytes) -> str:
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    async def list_keys(self, prefix: str) -> list[str]:
        pass
