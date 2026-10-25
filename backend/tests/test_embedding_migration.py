from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from test_semantic_retrieval import FakeSession, Sessions, note

from app.core.config import Settings
from app.infrastructure.database.migrate_embedding_dimensions import migrate


class DimensionSettingsTests(TestCase):
    def test_default_and_optional_local_sizes(self):
        self.assertEqual(Settings(_env_file=None).embedding_dimensions, 2048)
        self.assertEqual(
            Settings(_env_file=None, EMBEDDING_PROVIDER="ollama").embedding_dimensions, 768
        )


class DimensionMigrationTests(IsolatedAsyncioTestCase):
    async def test_old_index_is_invalidated_before_column_change_and_notes_requeued(self):
        session = FakeSession("vector(768)")
        target = note()
        result = MagicMock()
        result.all.return_value = [target]
        session.scalars = AsyncMock(return_value=result)
        with (
            patch(
                "app.infrastructure.database.migrate_embedding_dimensions.async_session_maker",
                Sessions(session),
            ),
            patch(
                "app.infrastructure.database.migrate_embedding_dimensions.get_settings",
                return_value=Settings(_env_file=None),
            ),
            patch(
                "app.infrastructure.database.migrate_embedding_dimensions.enqueue_note",
                new_callable=AsyncMock,
            ) as enqueue,
        ):
            self.assertEqual(await migrate(), 1)
            enqueue.assert_awaited_once_with(session, target)
        statements = [str(call.args[0]) for call in session.execute.call_args_list]
        self.assertLess(
            statements.index("DELETE FROM note_sections"),
            statements.index("ALTER TABLE note_sections ALTER COLUMN embedding TYPE vector(2048)"),
        )
        self.assertFalse(
            any("DELETE FROM notes" in sql or "DROP TABLE" in sql for sql in statements)
        )

    async def test_current_or_fresh_schema_is_unchanged(self):
        for current in (None, "vector(2048)"):
            session = FakeSession(current)
            with (
                patch(
                    "app.infrastructure.database.migrate_embedding_dimensions.async_session_maker",
                    Sessions(session),
                ),
                patch(
                    "app.infrastructure.database.migrate_embedding_dimensions.get_settings",
                    return_value=Settings(_env_file=None),
                ),
            ):
                self.assertEqual(await migrate(), 0)
            self.assertFalse(
                any(
                    "ALTER" in str(call.args[0]) or "DELETE" in str(call.args[0])
                    for call in session.execute.call_args_list
                )
            )
