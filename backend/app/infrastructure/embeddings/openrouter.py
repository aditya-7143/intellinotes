"""Hosted embeddings through OpenRouter, behind the application's embedding port."""

import logging

import httpx

from app.application.embeddings import validate_vectors
from app.core.config import get_settings
from app.core.exceptions import LLMProviderError
from app.core.logging import log_operation

logger = logging.getLogger("intellinotes.embeddings.openrouter")


class OpenRouterEmbeddingProvider:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        settings = get_settings()
        self.api_key = settings.OPENROUTER_API_KEY
        if not self.api_key:
            raise LLMProviderError("Set OPENROUTER_API_KEY to use hosted embeddings")
        self.model = settings.EMBEDDING_MODEL or "nvidia/nemotron-3-embed-1b:free"
        self.dimensions = settings.embedding_dimensions
        self.is_nemotron = self.model in {
            "nvidia/nemotron-3-embed-1b:free",
            "nvidia/nemotron-3.5-embed-1b:free",
        }
        self.base_url = (settings.EMBEDDING_BASE_URL or settings.OPENROUTER_BASE_URL).rstrip("/")
        task = ":query-passage-v1" if self.is_nemotron else ""
        self.model_key = (
            f"openrouter:{self.model}:{self.dimensions}:sections-v3-file-references{task}"
        )
        self.transport = transport

    @log_operation("embeddings.generate")
    async def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
            "provider": {"require_parameters": True},
        }
        if self.is_nemotron:
            # Use native output size; the endpoint handles task-specific formatting.
            payload["input_type"] = "query" if query else "passage"
        else:
            payload["dimensions"] = self.dimensions
        logger.debug(
            "embedding request model=%s task=%s batch_size=%d expected_dimensions=%d",
            self.model,
            "query" if query else "passage",
            len(texts),
            self.dimensions,
        )
        try:
            async with httpx.AsyncClient(timeout=120, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                logger.debug("embedding response status=%d", response.status_code)
                response.raise_for_status()
                data = response.json()["data"]
            if not isinstance(data, list) or len(data) != len(texts):
                raise ValueError("Invalid response count")
            indices = [item["index"] for item in data]
            if any(
                not isinstance(index, int) or isinstance(index, bool) for index in indices
            ) or sorted(indices) != list(range(len(texts))):
                raise ValueError("Invalid response indices")
            ordered = sorted(data, key=lambda item: item["index"])
            return validate_vectors(
                [item["embedding"] for item in ordered], len(texts), self.dimensions
            )
        except httpx.HTTPStatusError as error:
            raise LLMProviderError(
                f"OpenRouter embeddings returned HTTP {error.response.status_code}. "
                "Check the API key, credits, and embedding model configuration."
            ) from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            logger.debug("embedding transport_or_parse_failure error_type=%s", type(error).__name__)
            raise LLMProviderError(
                "OpenRouter embedding request failed or returned an invalid response."
            ) from None
