"""
Provider Base Classes

Abstract base class for all LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    """Configuration for a custom provider."""
    name: str  # unique identifier (e.g., "my-ollama")
    display_name: str  # human-readable name (e.g., "My Ollama")
    base_url: str  # API base URL
    api_key: str = ""  # optional API key
    models: list[str] = field(default_factory=list)  # available models
    default_model: str = ""  # default model to use

    def __post_init__(self):
        if not self.default_model and self.models:
            self.default_model = self.models[0]


@dataclass
class ProviderInfo:
    """Provider information for API responses."""
    name: str
    display_name: str
    builtin: bool
    models: list[str]
    default_model: str
    base_url: str = ""  # hidden for builtin providers


class ModelProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement get_model() to return a
    PydanticAI-compatible model object.
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def display_name(self) -> str:
        return self.config.display_name

    @property
    def models(self) -> list[str]:
        return self.config.models

    @property
    def default_model(self) -> str:
        return self.config.default_model

    @abstractmethod
    def get_model(self, model_id: str | None = None) -> Any:
        """
        Get a PydanticAI-compatible model instance.

        Args:
            model_id: Model identifier. If None, uses default_model.

        Returns:
            A model object that can be used with PydanticAI Agent.
        """
        ...

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str | None, int | None]:
        """
        Test the provider connection.

        Returns:
            Tuple of (success, error_message, latency_ms)
        """
        ...

    def to_info(self, builtin: bool = False) -> ProviderInfo:
        """Convert to ProviderInfo for API responses."""
        return ProviderInfo(
            name=self.name,
            display_name=self.display_name,
            builtin=builtin,
            models=self.models,
            default_model=self.default_model,
            base_url="" if builtin else self.config.base_url,
        )
