import tempfile
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_semantic_retrieval import FakeSession, Sessions

from app.api.v1.deps import get_current_user_id, get_folder_repo
from app.api.v1.folders import router
from app.application.use_cases.folders import (
    CreateFolderUseCase,
    DeleteFolderUseCase,
    UpdateFolderUseCase,
)
from app.application.use_cases.notes import UpdateNoteUseCase
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.models import Note
from app.infrastructure.database.migrate_storage_folders import migrate
from app.infrastructure.database.session import Base
from app.infrastructure.repositories.folder_repo import StorageFolderRepository
from app.infrastructure.storage.local_storage import LocalStorage
from app.infrastructure.storage.s3_storage import S3Storage


class SchemaTests(TestCase):
    def test_no_folder_table_or_foreign_key(self):
        self.assertNotIn("folders", Base.metadata.tables)
        self.assertNotIn("folder_id", Note.__table__.columns)


class FolderTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = LocalStorage(self.directory.name)
        self.repo = StorageFolderRepository(self.storage)
        self.user = uuid4()
        self.create = CreateFolderUseCase(self.repo)

    async def test_empty_and_external_directories_are_discovered_per_user(self):
        await self.create.execute(self.user, "Backend")
        await self.create.execute(self.user, "Security", "/Backend")
        Path(self.directory.name, str(self.user), "External").mkdir()
        await self.create.execute(uuid4(), "Private")
        self.assertEqual(
            await self.repo.get_paths(self.user), ["/Backend", "/Backend/Security", "/External"]
        )

    async def test_create_and_delete_empty_folder(self):
        await self.create.execute(self.user, "Empty")
        self.assertTrue(await DeleteFolderUseCase(self.repo).execute("/Empty", self.user))
        self.assertEqual(await self.repo.get_paths(self.user), [])

    async def test_nonempty_folder_cannot_be_deleted(self):
        await self.create.execute(self.user, "Keep")
        await self.storage.save(f"{self.user}/Keep/note.md", b"Keep me")
        with self.assertRaises(ConflictError):
            await DeleteFolderUseCase(self.repo).execute("/Keep", self.user)
        self.assertEqual(await self.storage.get(f"{self.user}/Keep/note.md"), b"Keep me")

    async def test_missing_parent_and_unsafe_names_are_rejected(self):
        with self.assertRaises(NotFoundError):
            await self.create.execute(self.user, "Child", "/Missing")
        for name in ("..", "../other", "x/y"):
            with self.assertRaises(ValidationError):
                await self.create.execute(self.user, name)

    async def test_symlink_to_other_user_is_not_accessible(self):
        other = uuid4()
        await self.create.execute(other, "Secret")
        await self.create.execute(self.user, "Normal")
        Path(self.directory.name, str(self.user), "Link").symlink_to(
            Path(self.directory.name, str(other))
        )
        self.assertNotIn("/Link", await self.repo.get_paths(self.user))
        with self.assertRaises(ValidationError):
            await self.storage.create_folder(f"{self.user}/Link/Injected")

    async def prepare_move(self):
        await self.create.execute(self.user, "Backend")
        await self.create.execute(self.user, "Security", "/Backend")
        target = Note(
            id=uuid4(),
            user_id=self.user,
            title="Auth",
            content="Text",
            folder_path="/Backend/Security",
            tags=[],
            storage_key=f"{self.user}/Backend/Security/Auth.md",
        )
        await self.storage.save(target.storage_key, b"Text")
        notes, transaction = AsyncMock(), AsyncMock()
        notes.get_by_user.return_value = [target]
        return target, notes, transaction, UpdateFolderUseCase(self.repo, notes, transaction)

    async def test_rename_moves_descendants_and_updates_note_references(self):
        target, notes, transaction, use_case = await self.prepare_move()
        result = await use_case.execute("/Backend", self.user, "Server")
        self.assertEqual(result.path, "/Server")
        self.assertEqual(target.folder_path, "/Server/Security")
        self.assertEqual(await self.storage.get(target.storage_key), b"Text")
        self.assertFalse(await self.storage.exists(f"{self.user}/Backend/Security/Auth.md"))
        notes.update.assert_awaited_once_with(target)
        transaction.commit.assert_awaited_once()

    async def test_failed_commit_restores_directory(self):
        _, _, transaction, use_case = await self.prepare_move()
        transaction.commit.side_effect = RuntimeError("DB unavailable")
        with self.assertRaises(RuntimeError):
            await use_case.execute("/Backend", self.user, "Server")
        self.assertEqual(await self.storage.get(f"{self.user}/Backend/Security/Auth.md"), b"Text")
        self.assertNotIn("/Server", await self.repo.get_paths(self.user))

    async def test_rename_collision_keeps_both_directories(self):
        _, _, _, use_case = await self.prepare_move()
        await self.create.execute(self.user, "Server")
        with self.assertRaises(ConflictError):
            await use_case.execute("/Backend", self.user, "Server")
        self.assertEqual(await self.storage.get(f"{self.user}/Backend/Security/Auth.md"), b"Text")
        self.assertIn("/Server", await self.repo.get_paths(self.user))

    async def test_migration_missing_file_aborts_before_removing_table(self):
        session = FakeSession("folders", False)
        rows = MagicMock()
        rows.mappings.return_value.all.return_value = []
        session.execute.return_value = rows
        notes = MagicMock()
        notes.all.return_value = [
            Note(
                id=uuid4(),
                user_id=self.user,
                title="Missing",
                folder_path="/",
                storage_key=f"{self.user}/Missing.md",
            )
        ]
        session.scalars = AsyncMock(return_value=notes)
        with (
            patch(
                "app.infrastructure.database.migrate_storage_folders.async_session_maker",
                Sessions(session),
            ),
            patch(
                "app.infrastructure.database.migrate_storage_folders.get_storage",
                return_value=self.storage,
            ),
        ):
            with self.assertRaises(ConflictError):
                await migrate()
        self.assertFalse(
            any("DROP" in str(call.args[0]) for call in session.execute.call_args_list)
        )

    async def test_move_to_root_and_into_own_subtree(self):
        _, _, _, use_case = await self.prepare_move()
        with self.assertRaises(ConflictError):
            await use_case.execute("/Backend", self.user, parent_path="/Backend/Security")
        result = await use_case.execute("/Backend/Security", self.user, parent_path="/")
        self.assertEqual(result.path, "/Security")

    async def test_note_can_be_moved_to_root_with_path(self):
        target, notes, _, _ = await self.prepare_move()
        notes.get_by_id.return_value = target
        notes.get_by_storage_key.return_value = None
        notes.update.side_effect = lambda note: note
        result = await UpdateNoteUseCase(notes, self.repo, self.storage).execute(
            target.id, self.user, folder_path="/"
        )
        self.assertEqual(result.folder_path, "/")
        self.assertEqual(await self.storage.get(f"{self.user}/Auth.md"), b"Text")

    async def test_folder_api_uses_path_and_preserves_empty_directories(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user_id] = lambda: self.user
        app.dependency_overrides[get_folder_repo] = lambda: self.repo
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/folders", json={"name": "Empty", "parent_path": "/"})
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()["path"], "/Empty")
            self.assertNotIn("id", created.json())
            self.assertEqual((await client.get("/folders")).json()[0]["parent_path"], "/")
            self.assertEqual(
                (await client.get("/folders/item", params={"path": "/Empty"})).status_code, 200
            )

    async def test_migration_preserves_legacy_empty_folders_before_drop(self):
        session = FakeSession("folders", False)
        rows = MagicMock()
        rows.mappings.return_value.all.return_value = [
            {"user_id": self.user, "path": "/Empty/Nested"}
        ]
        session.execute.return_value = rows
        notes = MagicMock()
        notes.all.return_value = []
        session.scalars = AsyncMock(return_value=notes)
        with (
            patch(
                "app.infrastructure.database.migrate_storage_folders.async_session_maker",
                Sessions(session),
            ),
            patch(
                "app.infrastructure.database.migrate_storage_folders.get_storage",
                return_value=self.storage,
            ),
        ):
            self.assertEqual(await migrate(), 1)
        self.assertEqual(await self.repo.get_paths(self.user), ["/Empty", "/Empty/Nested"])
        self.assertTrue(
            any(
                str(call.args[0]) == "DROP TABLE folders" for call in session.execute.call_args_list
            )
        )


class S3FolderTests(IsolatedAsyncioTestCase):
    async def test_prefix_markers_preserve_empty_folders_and_user_boundary(self):
        with patch("app.infrastructure.storage.s3_storage.boto3.client") as factory:
            storage = S3Storage(bucket="test")
            client = factory.return_value
            client.get_paginator.return_value.paginate.return_value = [
                {
                    "Contents": [
                        {"Key": "user/Empty/"},
                        {"Key": "user/Deep/Child/note.md"},
                        {"Key": "user-other/Private/note.md"},
                    ]
                }
            ]
            self.assertEqual(
                await storage.list_folders("user"), ["user/Deep", "user/Deep/Child", "user/Empty"]
            )
            client.get_paginator.return_value.paginate.assert_called_with(
                Bucket="test", Prefix="user/"
            )
            storage.exists = AsyncMock(return_value=False)
            await storage.create_folder("user/New")
            client.put_object.assert_called_with(Bucket="test", Key="user/New/", Body=b"")
