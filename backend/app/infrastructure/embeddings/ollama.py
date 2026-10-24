"""LangChain's Ollama integration behind the application's embedding port."""

import httpx
from langchain_ollama import OllamaEmbeddings
from ollama import ResponseError

from app.application.embeddings import validate_vectors
from app.core.config import get_settings
from app.core.exceptions import LLMProviderError
from app.core.logging import log_operation


class OllamaEmbeddingProvider:
    def __init__(self):
        settings = get_settings()
        self.model = settings.EMBEDDING_MODEL
        # Chunking changes require a fresh index; do not mix old and new chunks.
        self.model_key = f"ollama:{self.model}:768:sections-v2-langchain"
        self.client = OllamaEmbeddings(
            model=self.model,
            base_url=settings.EMBEDDING_BASE_URL,
            client_kwargs={"timeout": 120},
        )

    @log_operation("embeddings.generate")
    async def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        # Nomic's task prefixes are model-specific, not applied by the integration.
        prefix = "search_query: " if query else "search_document: "
        try:
            vectors = await self.client.aembed_documents([prefix + text for text in texts])
            return validate_vectors(vectors, len(texts))
        except (httpx.HTTPError, ResponseError, ValueError, TypeError, AttributeError) as error:
            raise LLMProviderError(
                "Embedding request failed. Check Ollama and the configured embedding model."
            ) from error
