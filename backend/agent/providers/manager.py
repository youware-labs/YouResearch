"""
Provider Manager

Central manager for all LLM providers (builtin and user-defined).
"""

from typing import Any

from agent.providers.base import ModelProvider, ProviderConfig, ProviderInfo
from agent.providers.config import (
    load_config,
    save_config,
    provider_config_from_dict,
    provider_config_to_dict,
)
from agent.providers.openai_compatible import OpenAICompatibleProvider


# Singleton instance
_manager: "ProviderManager | None" = None


def get_provider_manager() -> "ProviderManager":
    """Get the singleton ProviderManager instance."""
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager


def reset_provider_manager() -> None:
    """Reset the singleton (for testing)."""
    global _manager
    _manager = None


class ProviderManager:
    """
    Manages all LLM providers.

    Handles:
    - Loading/saving provider configuration
    - Registering builtin providers
    - CRUD operations for custom providers
    - Getting the active provider
    """

    def __init__(self):
        self._builtin_providers: dict[str, ModelProvider] = {}
        self._custom_providers: dict[str, ModelProvider] = {}
        self._active_provider: str = "openrouter"

        # Register builtin providers
        self._register_builtin_providers()

        # Load custom providers from config
        self._load_from_config()

    def _register_builtin_providers(self) -> None:
        """Register all builtin providers."""
        # Import here to avoid circular imports
        from agent.providers.openrouter import OpenRouterProvider

        openrouter = OpenRouterProvider()
        self._builtin_providers[openrouter.name] = openrouter

    def _load_from_config(self) -> None:
        """Load custom providers and active provider from config file."""
        config = load_config()

        # Load active provider
        self._active_provider = config.get("active_provider", "openrouter")

        # Load custom providers
        for name, data in config.get("providers", {}).items():
            try:
                provider_config = provider_config_from_dict(name, data)
                provider = OpenAICompatibleProvider(provider_config)
                self._custom_providers[name] = provider
            except Exception:
                # Skip invalid providers
                pass

        # Validate active provider exists
        if self._active_provider not in self._builtin_providers and \
           self._active_provider not in self._custom_providers:
            self._active_provider = "openrouter"

    def _save_to_config(self) -> None:
        """Save current state to config file."""
        providers_data = {}
        for name, provider in self._custom_providers.items():
            providers_data[name] = provider_config_to_dict(provider.config)

        config = {
            "providers": providers_data,
            "active_provider": self._active_provider,
        }
        save_config(config)

    def list_providers(self) -> list[ProviderInfo]:
        """
        List all available providers.

        Returns:
            List of ProviderInfo for all builtin and custom providers.
        """
        providers = []

        # Builtin providers first
        for provider in self._builtin_providers.values():
            providers.append(provider.to_info(builtin=True))

        # Then custom providers
        for provider in self._custom_providers.values():
            providers.append(provider.to_info(builtin=False))

        return providers

    def get_provider(self, name: str) -> ModelProvider:
        """
        Get a provider by name.

        Args:
            name: Provider name

        Returns:
            ModelProvider instance

        Raises:
            ValueError: If provider not found
        """
        if name in self._builtin_providers:
            return self._builtin_providers[name]
        if name in self._custom_providers:
            return self._custom_providers[name]
        raise ValueError(f"Provider not found: {name}")

    def get_active(self) -> ModelProvider:
        """
        Get the currently active provider.

        Returns:
            The active ModelProvider instance
        """
        return self.get_provider(self._active_provider)

    def get_active_name(self) -> str:
        """Get the name of the active provider."""
        return self._active_provider

    def set_active(self, name: str) -> None:
        """
        Set the active provider.

        Args:
            name: Provider name

        Raises:
            ValueError: If provider not found
        """
        # Validate provider exists
        self.get_provider(name)
        self._active_provider = name
        self._save_to_config()

    def add_provider(self, config: ProviderConfig) -> None:
        """
        Add a custom provider.

        Args:
            config: Provider configuration

        Raises:
            ValueError: If provider name conflicts with builtin or already exists
        """
        if config.name in self._builtin_providers:
            raise ValueError(f"Cannot override builtin provider: {config.name}")
        if config.name in self._custom_providers:
            raise ValueError(f"Provider already exists: {config.name}")

        provider = OpenAICompatibleProvider(config)
        self._custom_providers[config.name] = provider
        self._save_to_config()

    def update_provider(self, name: str, config: ProviderConfig) -> None:
        """
        Update an existing custom provider.

        Args:
            name: Provider name to update
            config: New configuration

        Raises:
            ValueError: If provider not found or is builtin
        """
        if name in self._builtin_providers:
            raise ValueError(f"Cannot modify builtin provider: {name}")
        if name not in self._custom_providers:
            raise ValueError(f"Provider not found: {name}")

        # If name is changing, handle the rename
        if config.name != name:
            del self._custom_providers[name]
            # Update active if needed
            if self._active_provider == name:
                self._active_provider = config.name

        provider = OpenAICompatibleProvider(config)
        self._custom_providers[config.name] = provider
        self._save_to_config()

    def remove_provider(self, name: str) -> None:
        """
        Remove a custom provider.

        Args:
            name: Provider name

        Raises:
            ValueError: If provider not found or is builtin
        """
        if name in self._builtin_providers:
            raise ValueError(f"Cannot remove builtin provider: {name}")
        if name not in self._custom_providers:
            raise ValueError(f"Provider not found: {name}")

        del self._custom_providers[name]

        # Reset active to openrouter if we removed the active provider
        if self._active_provider == name:
            self._active_provider = "openrouter"

        self._save_to_config()

    async def test_provider(self, name: str) -> dict[str, Any]:
        """
        Test a provider's connection.

        Args:
            name: Provider name

        Returns:
            Dict with 'success', 'error', and 'latency_ms' keys
        """
        provider = self.get_provider(name)
        success, error, latency_ms = await provider.test_connection()
        return {
            "success": success,
            "error": error,
            "latency_ms": latency_ms,
        }
