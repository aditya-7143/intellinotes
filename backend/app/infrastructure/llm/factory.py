from app.core.config import get_settings
from app.infrastructure.llm.anthropic_provider import AnthropicProvider
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.ollama_provider import OllamaProvider
from app.infrastructure.llm.openai_provider import OpenAIProvider
from app.infrastructure.llm.openrouter_provider import OpenRouterProvider

settings = get_settings()


def get_llm_provider() -> BaseLLMProvider:
    match settings.LLM_PROVIDER:
        case "ollama":
            return OllamaProvider()
        case "openai":
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not configured")
            return OpenAIProvider()
        case "anthropic":
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            return AnthropicProvider()
        case "openrouter":
            if not settings.OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY not configured")
            return OpenRouterProvider()
        case _:
            raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
