import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def main():
    """Launch the Streamlit GUI in a local browser."""
    project_root = Path(__file__).resolve().parent
    gui_path = project_root / "src" / "gui_app.py"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(gui_path),
            "--server.headless=true",
            "--server.port=8501",
        ],
        cwd=project_root,
    )

    time.sleep(2)
    webbrowser.open("http://localhost:8501")

    process.wait()


if __name__ == "__main__":
    main()
