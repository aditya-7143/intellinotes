import asyncio
import json
import logging
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.logging import (
    JsonFormatter,
    RequestLoggingMiddleware,
    configure_logging,
    log_operation,
    request_id,
)


class OperationTests(IsolatedAsyncioTestCase):
    async def test_async_logs_safe_counts_and_not_credentials_or_content(self):
        @log_operation("test.save")
        async def save(content, key, password, token, email, texts):
            return ["private-result"]

        with self.assertLogs("intellinotes", level="DEBUG") as logs:
            result = await save(
                "secret-note",
                "user/private-title.md",
                "secret-password",
                "secret-token",
                "secret-email",
                ["secret-input"],
            )
        output = "\n".join(logs.output)
        for value in (
            "secret-note",
            "private-title",
            "secret-password",
            "secret-token",
            "secret-email",
            "secret-input",
            "private-result",
        ):
            self.assertNotIn(value, output)
        self.assertIn("batch_size", output)
        self.assertIn("key_hash", output)
        self.assertIn("result_count=1", output)
        self.assertEqual(result, ["private-result"])

    async def test_failure_and_cancellation_are_rethrown_without_error_contents(self):
        for error in (ValueError("secret-provider-body"), asyncio.CancelledError("secret-cancel")):

            @log_operation("test.fail")
            async def fail():
                raise error

            with self.assertLogs("intellinotes", level="DEBUG") as logs:
                with self.assertRaises(type(error)):
                    await fail()
            self.assertIn(type(error).__name__, "\n".join(logs.output))
            self.assertNotIn("secret-", "\n".join(logs.output))

    async def test_request_ids_and_route_templates_hide_urls(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/notes/{note_id}")
        async def get_note(note_id: str):
            await asyncio.sleep(0)
            return {"request_id": request_id.get()}

        with self.assertLogs("intellinotes.http", level="DEBUG") as logs:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                responses = await asyncio.gather(
                    *[
                        client.get(
                            "/notes/private-title?q=private-query",
                            headers={"Authorization": "Bearer secret-token"},
                        )
                        for _ in range(2)
                    ]
                )
        ids = [response.headers["x-request-id"] for response in responses]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual([response.json()["request_id"] for response in responses], ids)
        self.assertEqual(request_id.get(), "-")
        output = "\n".join(logs.output)
        self.assertIn("/notes/{note_id}", output)
        for value in ("private-title", "private-query", "secret-token"):
            self.assertNotIn(value, output)


class LoggingTests(TestCase):
    def test_sync_decorator_preserves_results_and_signature(self):
        @log_operation("test.validate")
        def validate(content: str) -> int:
            return len(content)

        with self.assertLogs("intellinotes", level="DEBUG") as logs:
            self.assertEqual(validate("private"), 7)
        self.assertIn("completed", "\n".join(logs.output))
        self.assertNotIn("private", "\n".join(logs.output))

    def test_configuration_is_idempotent_and_honors_level(self):
        logger = logging.getLogger("intellinotes")
        old_handlers, old_level, old_propagate = logger.handlers[:], logger.level, logger.propagate
        try:
            logger.handlers = []
            with patch(
                "app.core.config.get_settings",
                return_value=Settings(_env_file=None, LOG_LEVEL="DEBUG"),
            ):
                configure_logging()
                configure_logging()
            self.assertEqual(len(logger.handlers), 1)
            self.assertEqual(logger.level, logging.DEBUG)
            record = logging.LogRecord("intellinotes.test", logging.DEBUG, "", 1, "done", (), None)
            payload = json.loads(JsonFormatter().format(record))
            self.assertEqual(payload["message"], "done")
            self.assertIn("request_id", payload)
        finally:
            logger.handlers, logger.level, logger.propagate = old_handlers, old_level, old_propagate
