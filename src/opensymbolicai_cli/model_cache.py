"""File-based cache for model lists with daily expiration."""

import json
import os
from datetime import date
from pathlib import Path

import httpx
from pydantic import BaseModel


class CachedModels(BaseModel):
    """Cached model list with date."""

    date: str
    provider: str
    models: list[str]


def _get_cache_dir() -> Path:
    """Get the cache directory for model lists."""
    cache_dir = Path.home() / ".cache" / "opensymbolicai-cli"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_cache_file(provider: str) -> Path:
    """Get the cache file path for a provider."""
    return _get_cache_dir() / f"models_{provider}.json"


def _is_cache_valid(cache_file: Path) -> bool:
    """Check if cache exists and was created today."""
    if not cache_file.exists():
        return False
    try:
        data = json.loads(cache_file.read_text())
        cached = CachedModels.model_validate(data)
        return cached.date == date.today().isoformat()
    except Exception:
        return False


def get_cached_models(provider: str) -> list[str] | None:
    """Get cached models for a provider if valid."""
    cache_file = _get_cache_file(provider)
    if not _is_cache_valid(cache_file):
        return None
    try:
        data = json.loads(cache_file.read_text())
        cached = CachedModels.model_validate(data)
        return cached.models
    except Exception:
        return None


def save_cached_models(provider: str, models: list[str]) -> None:
    """Save models to cache."""
    cache_file = _get_cache_file(provider)
    cached = CachedModels(
        date=date.today().isoformat(),
        provider=provider,
        models=models,
    )
    cache_file.write_text(cached.model_dump_json(indent=2))


async def fetch_ollama_models() -> list[str]:
    """Fetch models from local Ollama instance."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:11434/api/tags",
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()
        models = data.get("models", [])
        return [m["name"] for m in models]


async def fetch_openai_models() -> list[str]:
    """Fetch models from OpenAI API."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        models = [m["id"] for m in data.get("data", [])]
        # Filter to GPT models for usability
        gpt_models = [m for m in models if "gpt" in m.lower()]
        return sorted(gpt_models, reverse=True)


async def fetch_anthropic_models() -> list[str]:
    """Fetch models from Anthropic API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        models = [m["id"] for m in data.get("data", [])]
        return sorted(models, reverse=True)


async def fetch_fireworks_models() -> list[str]:
    """Fetch models from Fireworks API."""
    api_key = os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        raise ValueError("FIREWORKS_API_KEY not set")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.fireworks.ai/inference/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        models = [m["id"] for m in data.get("data", [])]
        return sorted(models)


async def fetch_groq_models() -> list[str]:
    """Fetch models from Groq API."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        models = [m["id"] for m in data.get("data", [])]

        # Filter to chat-compatible models only
        # Exclude: whisper (audio), guard (safety), compound (special), orpheus (TTS)
        excluded_patterns = (
            "whisper",
            "guard",
            "compound",
            "orpheus",
            "safeguard",
        )
        chat_models = [
            m for m in models if not any(pattern in m.lower() for pattern in excluded_patterns)
        ]

        return sorted(chat_models)


async def fetch_models_for_provider(provider: str) -> list[str]:
    """Fetch models for a provider, using cache if valid."""
    # Check cache first
    cached = get_cached_models(provider)
    if cached is not None:
        return cached

    # Fetch from API
    fetchers = {
        "ollama": fetch_ollama_models,
        "openai": fetch_openai_models,
        "anthropic": fetch_anthropic_models,
        "fireworks": fetch_fireworks_models,
        "groq": fetch_groq_models,
    }

    fetcher = fetchers.get(provider)
    if not fetcher:
        raise ValueError(f"Unknown provider: {provider}")

    models = await fetcher()

    # Save to cache
    save_cached_models(provider, models)

    return models
