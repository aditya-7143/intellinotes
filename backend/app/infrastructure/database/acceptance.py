"""Coordinate database acceptance with compensating storage writes."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports import StorageRepository
from app.core.exceptions import ConflictError, StorageError
from app.core.logging import log_operation
from app.domain.models import User

logger = logging.getLogger("intellinotes.acceptance")


class SQLAlchemyAcceptanceTransaction:
    def __init__(self, session: AsyncSession, storage: StorageRepository):
        self.session = session
        self.storage = storage
        self.before_images: dict[str, bytes | None] = {}

    @log_operation("infrastructure.database.acceptance.SQLAlchemyAcceptanceTransaction.lock_user")
    async def lock_user(self, user_id: UUID) -> None:
        # Serialize acceptance for one library, including newly-created destinations.
        await self.session.execute(select(User.id).where(User.id == user_id).with_for_update())

    @log_operation("infrastructure.database.acceptance.SQLAlchemyAcceptanceTransaction.save")
    async def save(self, key: str, content: bytes, expected: bytes | None) -> None:
        original = await self.storage.get(key)
        if original != expected:
            raise ConflictError(
                "Stored file has changed or already exists; regenerate the proposal"
            )
        self.before_images[key] = original
        await self.storage.save(key, content)

    @log_operation("infrastructure.database.acceptance.SQLAlchemyAcceptanceTransaction.commit")
    async def commit(self) -> None:
        await self.session.commit()
        self.before_images.clear()

    @log_operation("infrastructure.database.acceptance.SQLAlchemyAcceptanceTransaction.rollback")
    async def rollback(self) -> None:
        # Attempt all compensations even if the database or a storage write fails.
        failures = []
        try:
            await self.session.rollback()
        except Exception as error:
            failures.append(type(error).__name__)
        for key, original in reversed(list(self.before_images.items())):
            try:
                if original is None:
                    await self.storage.delete(key)
                    if await self.storage.exists(key):
                        raise StorageError("New file could not be removed")
                else:
                    await self.storage.save(key, original)
            except Exception as error:
                failures.append(type(error).__name__)
        self.before_images.clear()
        if failures:
            logger.error("Acceptance rollback incomplete error_types=%s", failures)
            raise StorageError("Acceptance failed and storage recovery needs attention")
