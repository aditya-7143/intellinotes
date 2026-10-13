import json
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.exceptions import LLMProviderError
from app.core.logging import log_operation
from app.infrastructure.llm.base import (
    REFINE_SYSTEM_PROMPT,
    STRUCTURE_SYSTEM_PROMPT,
    BaseLLMProvider,
)

settings = get_settings()


class OpenRouterProvider(BaseLLMProvider):
    def __init__(
        self, api_key: str | None = None, model: str | None = None, base_url: str | None = None
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.OPENROUTER_API_KEY,
            base_url=base_url or settings.OPENROUTER_BASE_URL,
        )
        self.model = model or settings.OPENROUTER_MODEL

    @log_operation("llm.structure_notes")
    async def structure_notes(self, snippet: str, context: Optional[str] = None) -> dict:
        user_prompt = f"Snippet:\n{snippet}"
        if context:
            user_prompt = f"Context: {context}\n\n{user_prompt}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            raise LLMProviderError(f"OpenRouter error: {str(e)}")

    @log_operation("llm.refine_structure")
    async def refine_structure(self, current_structure: dict, feedback: str) -> dict:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": REFINE_SYSTEM_PROMPT.format(
                            current_structure=json.dumps(current_structure, indent=2),
                            feedback=feedback,
                        ),
                    },
                    {
                        "role": "user",
                        "content": "Please refine the structure based on the feedback.",
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            raise LLMProviderError(f"OpenRouter error: {str(e)}")
