"""
OpenRouter Provider for PydanticAI

Provides access to various models through OpenRouter's OpenAI-compatible API.
Default provider for public users (clone the repo and use immediately).

Uses OpenAI-compatible API format.
"""

import os
from functools import cache

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default models - all support tool calling
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
HAIKU_MODEL = "anthropic/claude-sonnet-4.5"  # No Haiku available, fallback to Sonnet
SONNET_MODEL = "anthropic/claude-sonnet-4.5"
OPUS_MODEL = "anthropic/claude-sonnet-4.5"  # No Opus available, fallback to Sonnet

# Gemini model for vibe research
GEMINI_FLASH_MODEL = "google/gemini-3-flash-preview"

# All models with tool support
SUPPORTED_MODELS = [
    "anthropic/claude-sonnet-4.5",
    "openai/gpt-5.2",
    "google/gemini-3-flash-preview",
    "nvidia/nemotron-nano-9b-v2:free",  # Free model (no tool support)
]


@cache
def _cached_http_client(
    timeout: int = 300,
    connect: int = 5,
    read: int = 300,
) -> httpx.AsyncClient:
    """Create a cached HTTP client for connection pooling."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout=timeout, connect=connect, read=read),
    )


def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    client = _cached_http_client()
    if client.is_closed:
        _cached_http_client.cache_clear()
        client = _cached_http_client()
    return client


def get_openrouter_provider(api_key: str | None = None) -> OpenAIProvider:
    """Create an OpenAIProvider configured for OpenRouter."""
    if api_key is None:
        api_key = os.getenv("OPENROUTER_API_KEY", "")

    # Note: Empty API key will cause 401 error from OpenRouter API
    # This is intentional - we validate at request time, not import time

    return OpenAIProvider(
        openai_client=AsyncOpenAI(
            api_key=api_key or "not-configured",  # Placeholder to prevent client error
            base_url=OPENROUTER_BASE_URL,
            http_client=get_http_client(),
            default_headers={
                "HTTP-Referer": "https://github.com/ArcoCodes/OpenResearch",
                "X-Title": "OpenResearch LaTeX IDE",
            },
        )
    )


def get_openrouter_model(
    model_id: str | None = None,
    api_key: str | None = None,
) -> OpenAIModel:
    """
    Get a PydanticAI model configured for OpenRouter.

    Args:
        model_id: Model ID to use (default: anthropic/claude-sonnet-4)
        api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)

    Returns:
        Configured OpenAIModel instance for use with PydanticAI Agent
    """
    if model_id is None:
        model_id = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)

    provider = get_openrouter_provider(api_key)
    return OpenAIModel(model_id, provider=provider)


def get_default_model() -> OpenAIModel:
    """Get the default model (Claude Sonnet via OpenRouter)."""
    return get_openrouter_model(DEFAULT_MODEL)


def get_sonnet_model() -> OpenAIModel:
    """Get Claude Sonnet 4 model."""
    return get_openrouter_model(SONNET_MODEL)


def get_haiku_model() -> OpenAIModel:
    """Get Claude Haiku 3.5 model (faster, cheaper)."""
    return get_openrouter_model(HAIKU_MODEL)


def get_opus_model() -> OpenAIModel:
    """Get Claude Opus 4 model (most capable)."""
    return get_openrouter_model(OPUS_MODEL)


def get_gemini_flash_model() -> OpenAIModel:
    """Get Gemini 2.0 Flash model (cheaper, higher rate limits, good for vibe research)."""
    return get_openrouter_model(GEMINI_FLASH_MODEL)


def get_model(
    provider: str = "openrouter",
    model_id: str | None = None,
    api_key: str | None = None,
) -> OpenAIModel:
    """
    Get a model based on provider selection.

    This is the unified entry point for getting models from any supported provider.

    Args:
        provider: Provider name ("openrouter" or "dashscope")
        model_id: Model ID to use
        api_key: API key (required for dashscope)

    Returns:
        Configured Model instance for use with PydanticAI Agent

    Raises:
        ValueError: If provider is unknown or required params are missing
    """
    if provider == "openrouter":
        return get_openrouter_model(model_id=model_id, api_key=api_key)

    elif provider == "dashscope":
        if not api_key:
            raise ValueError("DashScope provider requires an API key")

        from agent.providers.dashscope import get_dashscope_model
        return get_dashscope_model(api_key=api_key, model_id=model_id)

    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Available providers: openrouter, dashscope"
        )
