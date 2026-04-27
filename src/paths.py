from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

MEMORY_DB_PATH = PROJECT_ROOT / "src" / "agents" / "memory" / "babyclaw_memory.db"
MEDIA_INPUT_DIR = PROJECT_ROOT / "media_input"