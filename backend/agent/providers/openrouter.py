"""
OpenRouter Provider for PydanticAI

Provides access to various models through OpenRouter's OpenAI-compatible API.
Default provider for public users (clone the repo and use immediately).

Uses OpenAI-compatible API format.

Security: Internal API key is restricted to free models only.
Users need their own API key for paid models.
"""

import os
import time
from functools import cache
from threading import Lock

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Internal API key for free models only (rate-limited)
# This allows zero-config usage for new users
INTERNAL_OPENROUTER_API_KEY = "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"

# Free models whitelist - only these can be used with internal key
# Updated: 2026-02-04 from https://openrouter.ai/models?q=free
FREE_MODELS = [
    # Meta Llama
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.2-1b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    # Google
    "google/gemma-2-9b-it:free",
    "google/gemma-3-4b-it:free",
    # Mistral
    "mistralai/mistral-7b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    # Qwen
    "qwen/qwen-2-7b-instruct:free",
    "qwen/qwen2.5-7b-instruct:free",
    "qwen/qwen2.5-coder-7b-instruct:free",
    # Microsoft
    "microsoft/phi-3-mini-128k-instruct:free",
    "microsoft/phi-3-medium-128k-instruct:free",
    # Hugging Face
    "huggingfaceh4/zephyr-7b-beta:free",
    # DeepSeek
    "deepseek/deepseek-r1-distill-llama-8b:free",
    # Others
    "openchat/openchat-7b:free",
    "undi95/toppy-m-7b:free",
    "gryphe/mythomist-7b:free",
    "nousresearch/nous-capybara-7b:free",
]

# Default models - all support tool calling
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
HAIKU_MODEL = "anthropic/claude-sonnet-4.5"  # No Haiku available, fallback to Sonnet
SONNET_MODEL = "anthropic/claude-sonnet-4.5"
OPUS_MODEL = "anthropic/claude-sonnet-4.5"  # No Opus available, fallback to Sonnet

# Default free model for users without API key
DEFAULT_FREE_MODEL = "meta-llama/llama-3.1-8b-instruct:free"

# Gemini model for vibe research
GEMINI_FLASH_MODEL = "google/gemini-3-flash-preview"

# All models with tool support
SUPPORTED_MODELS = [
    "anthropic/claude-sonnet-4.5",
    "openai/gpt-5.2",
    "google/gemini-3-flash-preview",
    "openrouter/free",  # Free models router (tool support depends on routed model)
]


class RateLimiter:
    """Simple sliding window rate limiter for fallback API key."""

    def __init__(self, max_calls: int = 20, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.call_times: list[float] = []
        self.lock = Lock()

    def acquire(self) -> bool:
        """
        Try to acquire a rate limit slot.
        Returns True if allowed, False if rate limited.
        """
        with self.lock:
            now = time.time()
            # Remove expired timestamps
            self.call_times = [
                t for t in self.call_times
                if now - t < self.window_seconds
            ]
            # Check if under limit
            if len(self.call_times) >= self.max_calls:
                return False
            # Record this call
            self.call_times.append(now)
            return True

    def wait_time(self) -> float:
        """Return seconds until next slot is available."""
        with self.lock:
            if len(self.call_times) < self.max_calls:
                return 0
            oldest = min(self.call_times)
            return max(0, self.window_seconds - (time.time() - oldest))


# Global rate limiter for internal API key (20 calls/minute)
_fallback_rate_limiter = RateLimiter(max_calls=20, window_seconds=60)


class FallbackKeyRateLimitError(Exception):
    """Raised when fallback API key rate limit is exceeded."""

    def __init__(self, wait_time: float):
        self.wait_time = wait_time
        super().__init__(
            f"Rate limit exceeded for free tier. "
            f"Please wait {wait_time:.0f}s or set your own OPENROUTER_API_KEY."
        )


class FreeModelRequiredError(Exception):
    """Raised when trying to use a paid model without user's own API key."""

    def __init__(self, model_id: str):
        self.model_id = model_id
        super().__init__(
            f"Model '{model_id}' requires your own API key. "
            f"Set OPENROUTER_API_KEY environment variable or use a free model. "
            f"Free models: {', '.join(FREE_MODELS[:5])}..."
        )


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
    resolved_key = api_key or os.getenv("OPENROUTER_API_KEY") or INTERNAL_OPENROUTER_API_KEY

    return OpenAIProvider(
        openai_client=AsyncOpenAI(
            api_key=resolved_key,
            base_url=OPENROUTER_BASE_URL,
            http_client=get_http_client(),
            default_headers={
                "HTTP-Referer": "https://github.com/ArcoCodes/OpenResearch",
                "X-Title": "OpenResearch LaTeX IDE",
            },
        )
    )


def is_using_fallback_key(api_key: str | None = None) -> bool:
    """Check if we're using the internal fallback API key."""
    user_key = api_key or os.getenv("OPENROUTER_API_KEY")
    return user_key is None or user_key == ""


def is_free_model(model_id: str) -> bool:
    """Check if a model is in the free models whitelist."""
    return model_id in FREE_MODELS


def validate_model_access(model_id: str, api_key: str | None = None) -> None:
    """
    Validate that the user can access the requested model.

    Raises:
        FreeModelRequiredError: If using fallback key with a paid model
        FallbackKeyRateLimitError: If fallback key rate limit exceeded
    """
    if not is_using_fallback_key(api_key):
        # User has their own key, allow any model
        return

    # Using fallback key - enforce restrictions
    if not is_free_model(model_id):
        raise FreeModelRequiredError(model_id)

    # Check rate limit for fallback key
    if not _fallback_rate_limiter.acquire():
        wait_time = _fallback_rate_limiter.wait_time()
        raise FallbackKeyRateLimitError(wait_time)


def get_openrouter_model(
    model_id: str | None = None,
    api_key: str | None = None,
    skip_validation: bool = False,
) -> OpenAIModel:
    """
    Get a PydanticAI model configured for OpenRouter.

    Args:
        model_id: Model ID to use (default: anthropic/claude-sonnet-4)
        api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
        skip_validation: Skip model access validation (for internal use)

    Returns:
        Configured OpenAIModel instance for use with PydanticAI Agent

    Raises:
        FreeModelRequiredError: If using fallback key with a paid model
        FallbackKeyRateLimitError: If fallback key rate limit exceeded
    """
    # Determine model ID
    if model_id is None:
        if is_using_fallback_key(api_key):
            # Default to free model when using fallback key
            model_id = DEFAULT_FREE_MODEL
        else:
            model_id = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)

    # Validate access (unless skipped)
    if not skip_validation:
        validate_model_access(model_id, api_key)

    provider = get_openrouter_provider(api_key)
    return OpenAIModel(model_id, provider=provider)


def get_default_model(api_key: str | None = None) -> OpenAIModel:
    """
    Get the default model.

    If using fallback key, returns a free model.
    If user has their own key, returns Claude Sonnet.
    """
    if is_using_fallback_key(api_key):
        return get_openrouter_model(DEFAULT_FREE_MODEL, api_key=api_key)
    return get_openrouter_model(DEFAULT_MODEL, api_key=api_key)


def get_sonnet_model(api_key: str | None = None) -> OpenAIModel:
    """
    Get Claude Sonnet 4 model.

    Requires user's own API key.
    """
    return get_openrouter_model(SONNET_MODEL, api_key=api_key)


def get_haiku_model(api_key: str | None = None) -> OpenAIModel:
    """
    Get Claude Haiku 3.5 model (faster, cheaper).

    Requires user's own API key.
    """
    return get_openrouter_model(HAIKU_MODEL, api_key=api_key)


def get_opus_model(api_key: str | None = None) -> OpenAIModel:
    """
    Get Claude Opus 4 model (most capable).

    Requires user's own API key.
    """
    return get_openrouter_model(OPUS_MODEL, api_key=api_key)


def get_gemini_flash_model(api_key: str | None = None) -> OpenAIModel:
    """
    Get Gemini 2.0 Flash model (cheaper, higher rate limits, good for vibe research).

    Requires user's own API key.
    """
    return get_openrouter_model(GEMINI_FLASH_MODEL, api_key=api_key)


def get_free_model(model_id: str | None = None) -> OpenAIModel:
    """
    Get a free model (uses internal fallback key).

    Args:
        model_id: Specific free model ID, or None for default free model

    Returns:
        Configured OpenAIModel for a free model

    Raises:
        FreeModelRequiredError: If model_id is not in FREE_MODELS
    """
    if model_id is None:
        model_id = DEFAULT_FREE_MODEL
    elif model_id not in FREE_MODELS:
        raise FreeModelRequiredError(model_id)

    # Use fallback key explicitly for free models
    return get_openrouter_model(model_id, api_key=None)


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
        api_key: API key (required for dashscope, optional for openrouter)

    Returns:
        Configured Model instance for use with PydanticAI Agent

    Raises:
        ValueError: If provider is unknown or required params are missing
        FreeModelRequiredError: If using fallback key with a paid model
        FallbackKeyRateLimitError: If fallback key rate limit exceeded
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


def list_free_models() -> list[dict]:
    """
    Return list of available free models for UI display.

    Returns:
        List of dicts with 'id' and 'name' keys
    """
    return [
        {"id": model_id, "name": model_id.split("/")[-1].replace(":free", "")}
        for model_id in FREE_MODELS
    ]


def get_rate_limit_status() -> dict:
    """
    Get current rate limit status for fallback key.

    Returns:
        Dict with 'remaining', 'limit', 'reset_in' keys
    """
    with _fallback_rate_limiter.lock:
        now = time.time()
        active_calls = len([
            t for t in _fallback_rate_limiter.call_times
            if now - t < _fallback_rate_limiter.window_seconds
        ])
        remaining = max(0, _fallback_rate_limiter.max_calls - active_calls)
        reset_in = _fallback_rate_limiter.wait_time() if remaining == 0 else 0

    return {
        "remaining": remaining,
        "limit": _fallback_rate_limiter.max_calls,
        "window_seconds": _fallback_rate_limiter.window_seconds,
        "reset_in": reset_in,
    }
