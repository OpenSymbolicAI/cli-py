"""OpenSymbolicAI CLI - Agent Runner TUI."""

from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file BEFORE other imports
# Search in current dir, then walk up to find .env
# Also check the package's parent directories (for development)
_package_dir = Path(__file__).parent.parent.parent  # src/opensymbolicai_cli -> src -> project root
_env_file = _package_dir / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
else:
    load_dotenv()  # Fall back to default behavior (cwd)

from opensymbolicai_cli.app import AgentRunnerApp  # noqa: E402


def main() -> None:
    """Entry point for the CLI."""
    app = AgentRunnerApp()
    app.run()


__all__ = ["main", "AgentRunnerApp"]
