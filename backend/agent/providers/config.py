"""
Provider Configuration Storage

Handles reading/writing provider configuration from ~/.youresearch/providers.json
"""

import json
from pathlib import Path
from typing import Any

from agent.providers.base import ProviderConfig


DEFAULT_CONFIG_DIR = Path.home() / ".youresearch"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "providers.json"


def get_config_path() -> Path:
    """Get the path to the providers config file."""
    return DEFAULT_CONFIG_FILE


def ensure_config_dir() -> None:
    """Ensure the config directory exists."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """
    Load provider configuration from disk.

    Returns:
        Config dict with 'providers' and 'active_provider' keys.
    """
    config_path = get_config_path()

    if not config_path.exists():
        return {
            "providers": {},
            "active_provider": "openrouter",
        }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure required keys exist
            if "providers" not in data:
                data["providers"] = {}
            if "active_provider" not in data:
                data["active_provider"] = "openrouter"
            return data
    except (json.JSONDecodeError, IOError):
        # Return default on error
        return {
            "providers": {},
            "active_provider": "openrouter",
        }


def save_config(config: dict[str, Any]) -> None:
    """
    Save provider configuration to disk.

    Args:
        config: Config dict with 'providers' and 'active_provider' keys.
    """
    ensure_config_dir()
    config_path = get_config_path()

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def provider_config_from_dict(name: str, data: dict[str, Any]) -> ProviderConfig:
    """
    Create a ProviderConfig from a dictionary.

    Args:
        name: Provider name (used as key in config)
        data: Provider data dict

    Returns:
        ProviderConfig instance
    """
    return ProviderConfig(
        name=name,
        display_name=data.get("display_name", name),
        base_url=data.get("base_url", ""),
        api_key=data.get("api_key", ""),
        models=data.get("models", []),
        default_model=data.get("default_model", ""),
    )


def provider_config_to_dict(config: ProviderConfig) -> dict[str, Any]:
    """
    Convert a ProviderConfig to a dictionary for storage.

    Args:
        config: ProviderConfig instance

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        "display_name": config.display_name,
        "base_url": config.base_url,
        "api_key": config.api_key,
        "models": config.models,
        "default_model": config.default_model,
    }
