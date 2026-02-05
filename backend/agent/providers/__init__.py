"""
Providers package for PydanticAI integration.

Supported providers:
- "openrouter" (default): OpenRouter API - access to Claude, GPT-4, Gemini, etc.
- Custom OpenAI-compatible providers: User-defined providers via UI

Usage:
    from agent.providers import get_provider_manager

    # Get the active provider's model
    manager = get_provider_manager()
    model = manager.get_active().get_model()

    # Or get a specific provider
    provider = manager.get_provider("my-ollama")
    model = provider.get_model("llama3")

Legacy usage (still supported):
    from agent.providers import get_default_model
    model = get_default_model()
"""

# Legacy exports (for backward compatibility)
from agent.providers.openrouter import (
    get_default_model,
    get_haiku_model,
    get_sonnet_model,
    get_opus_model,
    get_gemini_flash_model,
    get_model,
    get_openrouter_model,
    OpenRouterProvider,
)

# New provider system
from agent.providers.base import ModelProvider, ProviderConfig, ProviderInfo
from agent.providers.manager import get_provider_manager, reset_provider_manager
from agent.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    # Legacy
    "get_default_model",
    "get_haiku_model",
    "get_sonnet_model",
    "get_opus_model",
    "get_gemini_flash_model",
    "get_model",
    "get_openrouter_model",
    # New system
    "ModelProvider",
    "ProviderConfig",
    "ProviderInfo",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "get_provider_manager",
    "reset_provider_manager",
]
