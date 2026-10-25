import json
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMProviderError
from app.infrastructure.embeddings.factory import get_embedding_provider
from app.infrastructure.embeddings.openrouter import OpenRouterEmbeddingProvider


def vector(value=1.0):
    return [value] + [0.0] * 2047


class OpenRouterTests(IsolatedAsyncioTestCase):
    def provider(self, respond):
        settings = Settings(_env_file=None, OPENROUTER_API_KEY="test-key")
        with patch("app.infrastructure.embeddings.openrouter.get_settings", return_value=settings):
            return OpenRouterEmbeddingProvider(transport=httpx.MockTransport(respond))

    async def test_request_uses_same_key_and_dimensions_and_preserves_batch_order(self):
        def respond(request):
            self.assertEqual(str(request.url), "https://openrouter.ai/api/v1/embeddings")
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "nvidia/nemotron-3-embed-1b:free")
            self.assertNotIn("dimensions", body)
            self.assertEqual(body["input_type"], "query" if query else "passage")
            self.assertEqual(body["input"], ["auth", "fruit"])
            self.assertEqual(body["encoding_format"], "float")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": vector(-2)},
                        {"index": 0, "embedding": vector(2)},
                    ]
                },
            )

        provider = self.provider(respond)
        for query in (False, True):
            self.assertEqual(
                await provider.embed(["auth", "fruit"], query=query), [vector(), vector(-1)]
            )
        self.assertTrue(provider.model_key.startswith("openrouter:"))

    async def test_http_errors_are_redacted(self):
        for status in (401, 402, 429, 500):
            with self.subTest(status=status):
                provider = self.provider(
                    lambda request: httpx.Response(status, text="secret payload test-key")
                )
                with self.assertRaises(LLMProviderError) as caught:
                    await provider.embed(["private text"])
                self.assertIn(str(status), caught.exception.detail)
                self.assertNotIn("secret", caught.exception.detail)
                self.assertNotIn("test-key", caught.exception.detail)

    async def test_malformed_responses_are_rejected(self):
        for payload in (
            {},
            {"data": []},
            {"data": [{"index": 2, "embedding": vector()}]},
            {"data": [{"index": 0, "embedding": [1, 2]}]},
            {"data": [{"index": 0, "embedding": [1.0] + [0.0] * 767}]},
            {"data": [{"index": True, "embedding": vector()}]},
        ):
            with self.subTest(payload_type=type(payload)):
                provider = self.provider(lambda request: httpx.Response(200, json=payload))
                with self.assertRaises(LLMProviderError):
                    await provider.embed(["test"])

    async def test_transport_failure_and_empty_batch(self):
        def respond(request):
            raise httpx.ConnectError("private endpoint")

        provider = self.provider(respond)
        self.assertEqual(await provider.embed([]), [])
        with self.assertRaises(LLMProviderError) as caught:
            await provider.embed(["test"])
        self.assertNotIn("private", caught.exception.detail)


class FactoryTests(TestCase):
    def test_factory_selects_both_adapters(self):
        for name, module, cls in (
            ("openrouter", "openrouter", "OpenRouterEmbeddingProvider"),
            ("ollama", "ollama", "OllamaEmbeddingProvider"),
        ):
            settings = Settings(_env_file=None, EMBEDDING_PROVIDER=name)
            with (
                patch("app.infrastructure.embeddings.factory.get_settings", return_value=settings),
                patch(f"app.infrastructure.embeddings.{module}.{cls}") as adapter,
            ):
                self.assertIs(get_embedding_provider(), adapter.return_value)

    def test_missing_key_fails_without_network_request(self):
        with patch(
            "app.infrastructure.embeddings.openrouter.get_settings",
            return_value=Settings(_env_file=None, OPENROUTER_API_KEY=None),
        ):
            with self.assertRaises(LLMProviderError):
                OpenRouterEmbeddingProvider()
