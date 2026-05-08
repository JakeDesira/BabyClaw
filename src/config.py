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


def _read_positive_int_env(name: str, default_value: int) -> int:
    """Read a positive integer environment variable, falling back to ``default_value``."""
    raw_value = os.getenv(name, str(default_value))

    try:
        parsed = int(raw_value)
    except ValueError:
        return default_value

    if parsed <= 0:
        return default_value

    return parsed


PYTHON_RUN_TIMEOUT_SECONDS = _read_positive_int_env("BABYCLAW_PYTHON_RUN_TIMEOUT", 10)
MAX_ITERATIVE_STEPS = _read_positive_int_env("BABYCLAW_MAX_ITERATIVE_STEPS", 50)
