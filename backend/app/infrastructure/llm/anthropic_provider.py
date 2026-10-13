import json
from typing import Optional

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.core.exceptions import LLMProviderError
from app.core.logging import log_operation
from app.infrastructure.llm.base import (
    REFINE_SYSTEM_PROMPT,
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

    @log_operation("llm.refine_structure")
    async def refine_structure(self, current_structure: dict, feedback: str) -> dict:
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,
                system=REFINE_SYSTEM_PROMPT.format(
                    current_structure=json.dumps(current_structure, indent=2), feedback=feedback
                ),
                messages=[
                    {
                        "role": "user",
                        "content": "Please refine the structure based on the feedback.",
                    }
                ],
            )
            content = response.content[0].text if response.content else "{}"
            return json.loads(content)
        except Exception as e:
            raise LLMProviderError(f"Anthropic error: {str(e)}")
