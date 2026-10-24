import json
from typing import Optional

import ollama

from app.core.config import get_settings
from app.core.exceptions import LLMProviderError
from app.core.logging import log_operation
from app.infrastructure.llm.base import (
    STRUCTURE_SYSTEM_PROMPT,
    BaseLLMProvider,
)

settings = get_settings()


class OllamaProvider(BaseLLMProvider):
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.client = ollama.AsyncClient(host=base_url or settings.OLLAMA_BASE_URL)
        self.model = model or settings.OLLAMA_MODEL

    @log_operation("llm.structure_notes")
    async def structure_notes(self, snippet: str, context: Optional[str] = None) -> dict:
        user_prompt = f"Snippet:\n{snippet}"
        if context:
            user_prompt = f"Context: {context}\n\n{user_prompt}"

        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                format="json",
                options={"temperature": 0.3},
            )
            return json.loads(response["message"]["content"])
        except Exception as e:
            raise LLMProviderError(f"Ollama error: {str(e)}")
