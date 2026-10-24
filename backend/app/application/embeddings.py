"""Embedding contract and vector validation shared by query and document indexing."""

import math
from typing import Protocol

from app.core.exceptions import LLMProviderError

DIMENSIONS = 768


class EmbeddingProvider(Protocol):
    model_key: str

    async def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


def validate_vectors(vectors: list, count: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != count:
        raise LLMProviderError("Embedding provider returned an incorrect number of vectors")
    result = []
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != DIMENSIONS:
            raise LLMProviderError("Embedding provider must return 768-dimensional vectors")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            for value in vector
        ):
            raise LLMProviderError("Embedding provider returned invalid vector values")
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0 or not math.isfinite(norm):
            raise LLMProviderError("Embedding provider returned an invalid vector norm")
        result.append([value / norm for value in vector])
    return result
