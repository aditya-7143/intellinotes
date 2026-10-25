"""Small live smoke test using synthetic text, without indexing user files."""

import asyncio

from app.core.exceptions import LLMProviderError
from app.infrastructure.embeddings.factory import get_embedding_provider


async def main():
    try:
        provider = get_embedding_provider()
        documents = await provider.embed(
            [
                "Refresh tokens renew authentication sessions.",
                "Bananas are yellow fruit.",
            ]
        )
        query = (await provider.embed(["How do I refresh my login token?"], query=True))[0]
        scores = [sum(a * b for a, b in zip(query, document)) for document in documents]
        print(f"Provider/model: {provider.model_key}")
        print(f"Dimensions: {len(query)}; document vectors: {len(documents)}")
        print(f"Authentication similarity: {scores[0]:.4f}")
        print(f"Fruit similarity: {scores[1]:.4f}")
        if scores[0] <= scores[1]:
            raise SystemExit("Valid vectors received, but this relevance sanity check failed.")
        print("PASS: valid embeddings and expected relevance ordering")
    except LLMProviderError as error:
        raise SystemExit(error.detail) from None


if __name__ == "__main__":
    asyncio.run(main())
