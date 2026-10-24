import json
from typing import Optional

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.core.exceptions import LLMProviderError
from app.core.logging import log_operation
from app.infrastructure.llm.base import (
    STRUCTURE_SYSTEM_PROMPT,
    BaseLLMProvider,
)

settings = get_settings()


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = AsyncAnthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        self.model = model or settings.ANTHROPIC_MODEL

    @log_operation("llm.structure_notes")
    async def structure_notes(self, snippet: str, context: Optional[str] = None) -> dict:
        user_prompt = f"Snippet:\n{snippet}"
        if context:
            user_prompt = f"Context: {context}\n\n{user_prompt}"

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,
                system=STRUCTURE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            content = response.content[0].text if response.content else "{}"
            return json.loads(content)
        except Exception as e:
            raise LLMProviderError(f"Anthropic error: {str(e)}")
