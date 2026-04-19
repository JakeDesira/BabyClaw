from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

def get_current_time(timezone_name: str = "UTC") -> str:
    try:
        current_time = datetime.now(ZoneInfo(timezone_name))
        return current_time.strftime("%d %B %Y, %I:%M %p")
    except Exception:
        current_time = datetime.utcnow()
        return current_time.strftime("%d %B %Y, %I:%M %p UTC")

def read_file(path: str) -> str:
    file_path = Path(path)

    if not file_path.exists():
        return f"Error: File '{path}' does not exist."

    if not file_path.is_file():
        return f"Error: '{path}' is not a file."

    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file '{path}': {e}"


def list_directory(path: str = ".") -> str:
    dir_path = Path(path)

    if not dir_path.exists():
        return f"Error: Directory '{path}' does not exist."

    if not dir_path.is_dir():
        return f"Error: '{path}' is not a directory."

    try:
        items = [item.name for item in dir_path.iterdir()]
        return "\n".join(items) if items else "(empty directory)"
    except Exception as e:
        return f"Error listing directory '{path}': {e}"