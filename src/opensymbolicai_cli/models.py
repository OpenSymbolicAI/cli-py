"""Pydantic models for the CLI."""

import json
from pathlib import Path

from pydantic import BaseModel


class Agent(BaseModel):
    """Represents an agent that can be run."""

    id: str
    name: str
    description: str = ""
    status: str = "idle"


class AgentRun(BaseModel):
    """Represents a single run of an agent."""

    agent_id: str
    run_id: str
    status: str = "pending"
    output: str = ""


def _get_config_dir() -> Path:
    """Get the config directory for the CLI."""
    config_dir = Path.home() / ".config" / "opensymbolicai-cli"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _get_settings_file() -> Path:
    """Get the settings file path."""
    return _get_config_dir() / "settings.json"


class Settings(BaseModel):
    """Application settings."""

    agents_folder: Path | None = None
    default_provider: str = "ollama"
    default_model: str = ""
    debug_mode: bool = False

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from file, or return defaults."""
        settings_file = _get_settings_file()
        if settings_file.exists():
            try:
                data = json.loads(settings_file.read_text())
                return cls.model_validate(data)
            except Exception:
                return cls()
        return cls()

    def save(self) -> None:
        """Save settings to file."""
        settings_file = _get_settings_file()
        settings_file.write_text(self.model_dump_json(indent=2))


class ModelInfo(BaseModel):
    """Information about an available model."""

    name: str
    provider: str
    description: str = ""
