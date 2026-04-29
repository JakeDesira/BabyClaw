import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        """Fallback dotenv loader used when python-dotenv is unavailable."""
        return False

from paths import PROJECT_ROOT


load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_PLANNING_MODEL = os.getenv("BABYCLAW_PLANNING_MODEL", "gemma4")
DEFAULT_REASONING_MODEL = os.getenv("BABYCLAW_REASONING_MODEL", "gpt-oss:20b")
BABYCLAW_DEBUG = os.getenv("BABYCLAW_DEBUG", "true").lower() == "true"
OLLAMA_SUPPORTS_THINK = os.getenv("OLLAMA_SUPPORTS_THINK", "false").lower() in {"true", "1", "yes", "y"}
