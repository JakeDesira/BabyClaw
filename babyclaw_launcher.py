import subprocess
import socket
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def wait_for_server(url: str, process: subprocess.Popen, timeout_seconds: int = 30) -> bool:
    """Wait until Streamlit is accepting local requests."""
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if process.poll() is not None:
            return False

        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)

    return False


def find_available_port(start_port: int = 8501, max_attempts: int = 20) -> int:
    """Return the first available localhost port from start_port upward."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue

            return port

    raise RuntimeError("No available Streamlit port found.")


def main():
    """Launch the Streamlit GUI in a local browser."""
    project_root = Path(__file__).resolve().parent
    gui_path = project_root / "src" / "gui_app.py"
    log_path = project_root / "babyclaw_streamlit.log"
    port = find_available_port()
    local_url = f"http://localhost:{port}"
    health_url = f"{local_url}/_stcore/health"

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(gui_path),
                "--server.headless=true",
                f"--server.port={port}",
            ],
            cwd=project_root,
            start_new_session=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

        if wait_for_server(health_url, process):
            webbrowser.open(local_url)
            print(f"BabyClaw GUI is running at {local_url}")
            print(f"Streamlit logs: {log_path}")
        else:
            print(f"Streamlit did not become ready automatically. Try opening {local_url}")
            print(f"Check Streamlit logs: {log_path}")


if __name__ == "__main__":
    main()
