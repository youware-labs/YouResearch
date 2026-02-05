"""
OpenAI-Compatible Provider

Generic provider for any OpenAI-compatible API (Ollama, LM Studio, Azure, etc.)
"""

import time
from typing import Any

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent.providers.base import ModelProvider, ProviderConfig


class OpenAICompatibleProvider(ModelProvider):
    """
    Provider for OpenAI-compatible APIs.

    Works with: Ollama, LM Studio, Azure OpenAI, Together AI, Groq,
    Anyscale, Fireworks, DashScope, and any other OpenAI-compatible service.
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        # Ensure base_url doesn't end with /
        if self.config.base_url.endswith("/"):
            self.config.base_url = self.config.base_url.rstrip("/")

    def _get_openai_provider(self) -> OpenAIProvider:
        """Create an OpenAIProvider for this custom provider."""
        return OpenAIProvider(
            openai_client=AsyncOpenAI(
                api_key=self.config.api_key or "not-needed",
                base_url=self.config.base_url,
            )
        )

    def get_model(self, model_id: str | None = None) -> OpenAIModel:
        """
        Get a PydanticAI OpenAI model instance.

        Args:
            model_id: Model identifier. If None, uses default_model.

        Returns:
            OpenAIModel configured for this provider.
        """
        model = model_id or self.default_model
        if not model:
            raise ValueError(f"No model specified and no default_model for provider '{self.name}'")

        provider = self._get_openai_provider()
        return OpenAIModel(model, provider=provider)

    async def test_connection(self) -> tuple[bool, str | None, int | None]:
        """
        Test the provider connection by calling /v1/models endpoint.

        Returns:
            Tuple of (success, error_message, latency_ms)
        """
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"

                # Try /v1/models endpoint (standard OpenAI)
                url = f"{self.config.base_url}/models"
                response = await client.get(url, headers=headers)

                latency_ms = int((time.monotonic() - start) * 1000)

                if response.status_code == 200:
                    return True, None, latency_ms
                else:
                    return False, f"HTTP {response.status_code}: {response.text[:100]}", latency_ms

        except httpx.ConnectError:
            return False, f"Connection refused: {self.config.base_url}", None
        except httpx.TimeoutException:
            return False, "Connection timeout", None
        except Exception as e:
            return False, str(e), None
