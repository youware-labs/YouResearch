"""
DashScope Provider for PydanticAI (阿里云百炼)

Provides access to Chinese models via Alibaba Cloud's DashScope platform:
- DeepSeek V3.2
- Qwen Max
- Kimi K2
- GLM-4.7

Uses OpenAI-compatible API format.
"""

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


# DashScope configuration
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Available models on DashScope
DASHSCOPE_MODELS = [
    {"id": "deepseek-v3.2", "name": "DeepSeek V3.2"},
    {"id": "qwen-max-latest", "name": "Qwen Max"},
    {"id": "kimi-k2-thinking", "name": "Kimi K2"},
    {"id": "glm-4.7", "name": "GLM-4.7"},
]

DEFAULT_DASHSCOPE_MODEL = "deepseek-v3.2"


def get_dashscope_provider(api_key: str) -> OpenAIProvider:
    """Create an OpenAIProvider configured for DashScope."""
    return OpenAIProvider(
        api_key=api_key,
        base_url=DASHSCOPE_BASE_URL,
    )


def get_dashscope_model(api_key: str, model_id: str | None = None) -> OpenAIModel:
    """
    Get a PydanticAI model configured for DashScope.

    Args:
        api_key: DashScope API key (from 阿里云百炼)
        model_id: Model ID to use (default: deepseek-v3.2)

    Returns:
        Configured OpenAIModel instance for use with PydanticAI Agent
    """
    if model_id is None:
        model_id = DEFAULT_DASHSCOPE_MODEL

    # Validate model ID
    valid_ids = [m["id"] for m in DASHSCOPE_MODELS]
    if model_id not in valid_ids:
        raise ValueError(
            f"Unknown DashScope model: {model_id}. "
            f"Available models: {', '.join(valid_ids)}"
        )

    provider = get_dashscope_provider(api_key)
    return OpenAIModel(model_id, provider=provider)


def list_dashscope_models() -> list[dict]:
    """Return list of available DashScope models."""
    return DASHSCOPE_MODELS.copy()
