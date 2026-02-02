"""
Providers package for PydanticAI integration.

Supported providers:
- "openrouter" (default): OpenRouter API - access to Claude, GPT-4, Gemini, etc.
- "dashscope": Alibaba Cloud DashScope - Chinese models (DeepSeek, Qwen, Kimi, GLM)

Set LLM_PROVIDER environment variable to switch providers:
- LLM_PROVIDER=openrouter (default)
"""

from agent.providers.openrouter import (
    get_default_model,
    get_haiku_model,
    get_sonnet_model,
    get_opus_model,
    get_gemini_flash_model,
    get_model,
    get_openrouter_model,
)

__all__ = [
    "get_default_model",
    "get_haiku_model",
    "get_sonnet_model",
    "get_opus_model",
    "get_gemini_flash_model",
    "get_model",
    "get_openrouter_model",
]
