from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from langchain_ollama import OllamaEmbeddings
from ollama import ResponseError
from sqlalchemy.dialects import postgresql

from app.application.embeddings import DIMENSIONS, validate_vectors
from app.core.exceptions import ConflictError, LLMProviderError
from app.domain.models import Note, NoteIndexJob, NoteSection
from app.infrastructure.embeddings.ollama import OllamaEmbeddingProvider
from app.infrastructure.rag.index import enqueue_note
from app.infrastructure.rag.retriever import SemanticSectionRetriever
from app.infrastructure.rag.worker import IndexWorker
from app.infrastructure.repositories.note_repo import SQLAlchemyNoteRepository


def vector():
    return [1.0] + [0.0] * (DIMENSIONS - 1)


def note(user=None, content="# GANs\nMode collapse reduces diversity."):
    target = Note(
        id=uuid4(),
        user_id=user or uuid4(),
        title="GANs",
        content=content,
        folder_path="/AI",
        tags=[],
        updated_at=datetime.now(timezone.utc),
    )
    target.storage_key = f"{target.user_id}/AI/GANs.md"
    return target


def embedding_provider():
    provider = SimpleNamespace(model_key=f"test:{DIMENSIONS}:v1", dimensions=DIMENSIONS)
    provider.embed = AsyncMock(side_effect=lambda texts, **kwargs: [vector() for _ in texts])
    return provider


class VectorTests(TestCase):
    def test_rejects_malformed_vectors(self):
        for vectors in [
            None,
            [],
            [[1]],
            [[0] * DIMENSIONS],
            [[float("nan")] * DIMENSIONS],
            [[True] * DIMENSIONS],
        ]:
            with self.subTest(vectors_type=type(vectors)), self.assertRaises(LLMProviderError):
                validate_vectors(vectors, 1)

    def test_normalizes_vectors(self):
        result = validate_vectors([[2.0] + [0] * (DIMENSIONS - 1)], 1)
        self.assertEqual(result, [vector()])


class EmbeddingTests(IsolatedAsyncioTestCase):
    async def test_real_langchain_integration_with_mock_ollama_transport(self):
        def respond(request):
            import json

            payload = json.loads(request.content)
            self.assertEqual(request.url.path, "/api/embed")
            self.assertEqual(payload["model"], "nomic-embed-text")
            self.assertEqual(payload["input"], ["search_query: varied outputs"])
            return httpx.Response(200, json={"embeddings": [([1.0] + [0.0] * 767)]})

        client = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url="http://ollama.test",
            async_client_kwargs={"transport": httpx.MockTransport(respond)},
        )
        with patch("app.infrastructure.embeddings.ollama.OllamaEmbeddings", return_value=client):
            self.assertEqual(
                await OllamaEmbeddingProvider().embed(["varied outputs"], query=True),
                [([1.0] + [0.0] * 767)],
            )

    async def test_langchain_receives_query_and_document_prefixes(self):
        client = MagicMock()
        client.aembed_documents = AsyncMock(return_value=[([1.0] + [0.0] * 767)])
        with patch(
            "app.infrastructure.embeddings.ollama.OllamaEmbeddings", return_value=client
        ) as factory:
            provider = OllamaEmbeddingProvider()
            self.assertEqual(
                await provider.embed(["low variety"], query=True), [([1.0] + [0.0] * 767)]
            )
            client.aembed_documents.assert_awaited_with(["search_query: low variety"])
            await provider.embed(["Mode collapse"])
            client.aembed_documents.assert_awaited_with(["search_document: Mode collapse"])
            self.assertEqual(factory.call_args.kwargs["client_kwargs"], {"timeout": 120})
            self.assertIn("sections-v3-file-references", provider.model_key)

    async def test_provider_error_does_not_expose_response_body(self):
        client = MagicMock()
        client.aembed_documents = AsyncMock(
            side_effect=ResponseError("sensitive note content", 500)
        )
        with patch("app.infrastructure.embeddings.ollama.OllamaEmbeddings", return_value=client):
            with self.assertRaises(LLMProviderError) as caught:
                await OllamaEmbeddingProvider().embed(["private note"])
        self.assertNotIn("sensitive", caught.exception.detail)

    async def test_transport_error_is_redacted(self):
        client = MagicMock()
        client.aembed_documents = AsyncMock(side_effect=httpx.ConnectError("private endpoint"))
        with patch("app.infrastructure.embeddings.ollama.OllamaEmbeddings", return_value=client):
            with self.assertRaises(LLMProviderError) as caught:
                await OllamaEmbeddingProvider().embed(["private note"])
        self.assertNotIn("private", caught.exception.detail)

    async def test_empty_batch_does_not_call_langchain(self):
        with patch("app.infrastructure.embeddings.ollama.OllamaEmbeddings") as factory:
            self.assertEqual(await OllamaEmbeddingProvider().embed([]), [])
            factory.return_value.aembed_documents.assert_not_called()


class SemanticRetrievalTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = AsyncMock()
        self.note = note()
        self.provider = embedding_provider()
        self.storage = AsyncMock()
        self.storage.get.return_value = self.note.content.encode()
        self.retriever = SemanticSectionRetriever(self.session, self.provider, self.storage)
        self.session.scalar.side_effect = [None, self.note.id]
        self.chunk = NoteSection(
            user_id=self.note.user_id,
            note_id=self.note.id,
            source_version=self.note.version,
            heading="GANs",
            start_offset=0,
            end_offset=len(self.note.content),
        )
        self.result = MagicMock()
        self.result.all.return_value = [(self.chunk, self.note)]
        self.session.execute.return_value = self.result

    async def test_semantic_query_uses_vectors_and_user_filter(self):
        results = await self.retriever.retrieve(self.note.user_id, "outputs all look alike")
        self.assertEqual(results[0].note.id, self.note.id)
        self.provider.embed.assert_awaited_once_with(["outputs all look alike"], query=True)
        statement = self.session.execute.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("<=>", sql)
        self.assertIn("note_sections.user_id", sql)
        self.assertIn("notes.user_id", sql)
        self.assertIn("embedding_model", sql)
        self.assertNotIn("ILIKE", sql)

    async def test_pending_or_failed_index_blocks_organization(self):
        self.session.scalar.side_effect = [self.note.id]
        with self.assertRaises(ConflictError):
            await self.retriever.retrieve(self.note.user_id, "query")
        self.provider.embed.assert_not_awaited()

    async def test_empty_library_needs_no_embeddings(self):
        self.session.scalar.side_effect = [None, None]
        self.assertEqual(await self.retriever.retrieve(self.note.user_id, "query"), [])
        self.provider.embed.assert_not_awaited()

    async def test_stale_section_cannot_become_an_edit_target(self):
        self.storage.get.return_value = b"Changed after indexing"
        with self.assertRaises(ConflictError):
            await self.retriever.retrieve(self.note.user_id, "query")

    async def test_long_queries_are_embedded_without_truncation(self):
        await self.retriever.retrieve(self.note.user_id, "diversity " * 400)
        texts = [text for call in self.provider.embed.call_args_list for text in call.args[0]]
        self.assertEqual("".join(texts), "diversity " * 400)
        self.assertTrue(all(len(text.encode()) <= 1200 for text in texts))

    async def test_cross_user_result_is_dropped(self):
        self.note.user_id = uuid4()
        self.assertEqual(await self.retriever.retrieve(self.chunk.user_id, "query"), [])


class QueueTests(IsolatedAsyncioTestCase):
    async def test_job_and_invalidation_use_callers_transaction(self):
        session = AsyncMock()
        await enqueue_note(session, note())
        self.assertEqual(session.execute.await_count, 2)
        sql = str(session.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
        self.assertIn("ON CONFLICT", sql)
        session.commit.assert_not_awaited()

    async def test_repository_update_queues_reindex(self):
        session = AsyncMock()
        target = note()
        with patch(
            "app.infrastructure.repositories.note_repo.enqueue_note", new_callable=AsyncMock
        ) as enqueue:
            await SQLAlchemyNoteRepository(session, AsyncMock()).update(target)
            enqueue.assert_awaited_once_with(session, target)
        session.commit.assert_not_awaited()

    async def test_repository_delete_removes_chunks_and_jobs(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = note()
        session.execute.return_value = result
        session.get.return_value = result.scalar_one_or_none.return_value
        await SQLAlchemyNoteRepository(session, AsyncMock()).delete(
            result.scalar_one_or_none.return_value.id
        )
        sql = [str(call.args[0]) for call in session.execute.call_args_list]
        self.assertTrue(any("DELETE FROM note_sections" in statement for statement in sql))
        self.assertTrue(any("DELETE FROM note_index_jobs" in statement for statement in sql))


class FakeSession:
    def __init__(self, *scalar_results):
        self.scalar = AsyncMock(side_effect=list(scalar_results))
        self.execute = AsyncMock()
        self.delete = AsyncMock()
        self.add = MagicMock()

    @asynccontextmanager
    async def begin(self):
        yield self


class Sessions:
    def __init__(self, *sessions):
        self.sessions = iter(sessions)

    @asynccontextmanager
    async def __call__(self):
        yield next(self.sessions)


class WorkerTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.note = note()
        self.job = NoteIndexJob(
            note_id=self.note.id,
            user_id=self.note.user_id,
            generation=uuid4(),
            attempts=0,
            status="pending",
        )
        self.claim = FakeSession(self.job)
        self.read = FakeSession(self.note)
        self.publish = FakeSession(self.note, self.job)
        self.provider = embedding_provider()
        self.storage = AsyncMock()
        self.storage.get.return_value = self.note.content.encode()

    async def test_publishes_complete_index_and_removes_job(self):
        worker = IndexWorker(
            Sessions(self.claim, self.read, self.publish), self.provider, self.storage
        )
        self.assertTrue(await worker.run_once())
        self.publish.delete.assert_awaited_once_with(self.job)
        chunk = self.publish.add.call_args.args[0]
        self.assertEqual(chunk.source_version, self.note.version)
        self.assertEqual(chunk.user_id, self.note.user_id)
        self.assertEqual(chunk.embedding_model, self.provider.model_key)
        self.assertEqual(chunk.embedding, vector())

    async def test_superseded_generation_never_publishes(self):
        newer_job = NoteIndexJob(note_id=self.note.id, generation=uuid4())
        self.publish = FakeSession(self.note, newer_job)
        await IndexWorker(
            Sessions(self.claim, self.read, self.publish), self.provider, self.storage
        ).run_once()
        self.publish.add.assert_not_called()
        self.publish.delete.assert_not_awaited()

    async def test_edit_during_embedding_requeues_instead_of_publishing(self):
        edited = note(self.note.user_id, "New content")
        edited.id = self.note.id
        self.publish = FakeSession(edited, self.job)
        with patch("app.infrastructure.rag.worker.enqueue_note", new_callable=AsyncMock) as enqueue:
            await IndexWorker(
                Sessions(self.claim, self.read, self.publish), self.provider, self.storage
            ).run_once()
            enqueue.assert_awaited_once_with(self.publish, edited)
        self.publish.add.assert_not_called()

    async def test_embedding_failure_is_retryable_and_redacted(self):
        self.provider.embed.side_effect = RuntimeError("private payload")
        failure = FakeSession(self.job)
        await IndexWorker(
            Sessions(self.claim, self.read, failure), self.provider, self.storage
        ).run_once()
        self.assertEqual(self.job.attempts, 1)
        self.assertEqual(self.job.last_error, "RuntimeError")
        self.assertIsNone(self.job.lease_until)
        self.assertGreater(self.job.available_at, datetime.now(timezone.utc) - timedelta(seconds=1))
        self.publish.add.assert_not_called()

    async def test_exhausted_job_requires_explicit_reindex(self):
        self.job.attempts = 7
        self.provider.embed.side_effect = RuntimeError()
        await IndexWorker(
            Sessions(self.claim, self.read, FakeSession(self.job)), self.provider, self.storage
        ).run_once()
        self.assertEqual(self.job.status, "failed")

    async def test_idle_worker_does_not_call_provider(self):
        self.assertFalse(
            await IndexWorker(Sessions(FakeSession(None)), self.provider, self.storage).run_once()
        )
        self.provider.embed.assert_not_awaited()
