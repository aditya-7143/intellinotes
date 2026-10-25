"""Select an embedding adapter without coupling retrieval or workers to a vendor."""

from app.application.embeddings import EmbeddingProvider
from app.core.config import get_settings


def get_embedding_provider() -> EmbeddingProvider:
    if get_settings().EMBEDDING_PROVIDER == "ollama":
        from app.infrastructure.embeddings.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider()
    from app.infrastructure.embeddings.openrouter import OpenRouterEmbeddingProvider

    return OpenRouterEmbeddingProvider()
