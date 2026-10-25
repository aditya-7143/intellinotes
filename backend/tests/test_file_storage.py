import tempfile
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

import test_semantic_retrieval as fixtures
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from test_semantic_retrieval import FakeSession, Sessions, note

from app.application.note_content import load_note_content
from app.core.exceptions import ConflictError, ValidationError
from app.domain.models import Note, NoteSection
from app.infrastructure.database.migrate_file_storage import migrate
from app.infrastructure.rag.reconcile import reconcile_files
from app.infrastructure.rag.worker import IndexWorker
from app.infrastructure.repositories.note_repo import SQLAlchemyNoteRepository
from app.infrastructure.storage.local_storage import LocalStorage


class SchemaTests(TestCase):
    def test_note_and_index_schema_do_not_store_body_text(self):
        self.assertNotIn("content", Note.__table__.columns)
        self.assertNotIn("content", NoteSection.__table__.columns)
        sql = str(CreateTable(NoteSection.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn("start_offset", sql)
        self.assertIn("end_offset", sql)
        self.assertIn("VECTOR(768)", sql)


class FileReadTests(IsolatedAsyncioTestCase):
    async def test_repository_returns_authoritative_file_and_searches_external_edits(self):
        target = note(content="Old transient value")
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalStorage(directory)
            await storage.save(target.storage_key, b"Fresh file content")
            session = AsyncMock()
            result = MagicMock()
            result.scalar_one_or_none.return_value = target
            result.scalars.return_value.all.return_value = [target]
            session.execute.return_value = result
            repository = SQLAlchemyNoteRepository(session, storage)
            loaded = await repository.get_by_id(target.id)
            self.assertEqual(loaded.content, "Fresh file content")
            previous_version = loaded.version
            await storage.save(target.storage_key, "Externally edited 🌍".encode())
            self.assertEqual(await repository.search(target.user_id, "externally"), [target])
            self.assertNotEqual(target.version, previous_version)

    async def test_missing_file_never_falls_back_to_memory(self):
        storage = AsyncMock()
        storage.get.return_value = None
        with self.assertRaises(ConflictError):
            await load_note_content(note(), storage)

    async def test_cross_user_reference_rejected_before_storage_read(self):
        target = note()
        target.storage_key = "someone-else/private.md"
        storage = AsyncMock()
        with self.assertRaises(ValidationError):
            await load_note_content(target, storage)
        storage.get.assert_not_awaited()


class FileIndexTests(IsolatedAsyncioTestCase):
    def setUp(self):
        fixtures.WorkerTests.setUp(self)

    async def test_offsets_reconstruct_unicode_file_without_stored_chunk_text(self):
        content = "# Unicode\n" + "hello 🌍\n" * 400
        self.storage.get.return_value = content.encode()
        await IndexWorker(
            Sessions(self.claim, self.read, self.publish), self.provider, self.storage
        ).run_once()
        chunks = [call.args[0] for call in self.publish.add.call_args_list]
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(content[c.start_offset : c.end_offset] for c in chunks), content)
        self.assertTrue(all(not hasattr(c, "content") for c in chunks))

    async def test_external_edit_during_embedding_requeues(self):
        self.storage.get.side_effect = [b"Original file", b"External edit"]
        with patch("app.infrastructure.rag.worker.enqueue_note", new_callable=AsyncMock) as enqueue:
            await IndexWorker(
                Sessions(self.claim, self.read, self.publish), self.provider, self.storage
            ).run_once()
            enqueue.assert_awaited_once()
        self.publish.add.assert_not_called()


class ReconcileTests(IsolatedAsyncioTestCase):
    async def test_scan_queues_external_change_but_leaves_current_index_alone(self):
        for changed in (False, True):
            with self.subTest(changed=changed):
                target = note()
                session = FakeSession(None, target.version)
                result = MagicMock()
                result.all.return_value = [target]
                session.scalars = AsyncMock(return_value=result)
                storage = AsyncMock()
                storage.get.return_value = (
                    b"External change" if changed else target.content.encode()
                )
                with patch(
                    "app.infrastructure.rag.reconcile.enqueue_note", new_callable=AsyncMock
                ) as enqueue:
                    count = await reconcile_files(Sessions(session), storage, "test")
                    self.assertEqual(count, int(changed))
                    self.assertEqual(enqueue.await_count, int(changed))


class MigrationTests(IsolatedAsyncioTestCase):
    async def test_missing_or_different_file_aborts_before_dropping_columns(self):
        for content in (None, b"Different external content"):
            with self.subTest(content=content):
                target = note()
                session = FakeSession(True)
                result = MagicMock()
                result.mappings.return_value.all.return_value = [
                    {
                        "id": target.id,
                        "user_id": target.user_id,
                        "storage_key": target.storage_key,
                        "content": target.content,
                    }
                ]
                session.execute.return_value = result
                storage = AsyncMock()
                storage.get.return_value = content
                with (
                    patch(
                        "app.infrastructure.database.migrate_file_storage.async_session_maker",
                        Sessions(session),
                    ),
                    patch(
                        "app.infrastructure.database.migrate_file_storage.get_storage",
                        return_value=storage,
                    ),
                ):
                    with self.assertRaises((RuntimeError, ConflictError)):
                        await migrate()
                self.assertFalse(
                    any(
                        "DROP COLUMN" in str(call.args[0])
                        for call in session.execute.call_args_list
                    )
                )
                storage.save.assert_not_awaited()

    async def test_verified_files_allow_migration_and_reindex(self):
        target = note()
        session = FakeSession(True)
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {
                "id": target.id,
                "user_id": target.user_id,
                "storage_key": target.storage_key,
                "content": target.content,
            }
        ]
        session.execute.return_value = result
        notes = MagicMock()
        notes.all.return_value = [target]
        session.scalars = AsyncMock(return_value=notes)
        storage = AsyncMock()
        storage.get.return_value = target.content.encode()
        with (
            patch(
                "app.infrastructure.database.migrate_file_storage.async_session_maker",
                Sessions(session),
            ),
            patch(
                "app.infrastructure.database.migrate_file_storage.get_storage", return_value=storage
            ),
            patch(
                "app.infrastructure.database.migrate_file_storage.enqueue_note",
                new_callable=AsyncMock,
            ) as enqueue,
        ):
            self.assertEqual(await migrate(), 1)
            enqueue.assert_awaited_once_with(session, target)
        self.assertTrue(
            any(
                "ALTER TABLE notes DROP COLUMN content" in str(call.args[0])
                for call in session.execute.call_args_list
            )
        )
        storage.save.assert_not_awaited()
