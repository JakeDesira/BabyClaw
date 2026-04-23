from pathlib import Path


class FilesystemGuard:
    def __init__(self):
        self.approved_directories: list[Path] = []
        self.active_directory: Path | None = None

    def request_approval(self, raw_path: str) -> str:
        resolved = Path(raw_path).expanduser().resolve()
        return (
            f"The agent is requesting access to:\n"
            f"  {resolved}\n\n"
            f"Type YES to approve or NO to deny."
        )

    def approve(self, raw_path: str) -> bool:
        resolved = Path(raw_path).expanduser().resolve()

        if not resolved.exists() or not resolved.is_dir():
            return False

        if resolved not in self.approved_directories:
            self.approved_directories.append(resolved)

        # Make the most recently approved directory the default working area
        self.active_directory = resolved
        return True

    def resolve_path(self, file_path: str | Path) -> Path:
        raw = Path(file_path).expanduser()

        # Relative paths should be treated as inside the active approved directory
        if not raw.is_absolute():
            if self.active_directory is not None:
                raw = self.active_directory / raw

        return raw.resolve()

    def is_approved(self, file_path: str | Path) -> bool:
        target = self.resolve_path(file_path)
        return any(
            target == approved or approved in target.parents
            for approved in self.approved_directories
        )

    def safe_path(self, file_path: str | Path) -> Path | None:
        target = self.resolve_path(file_path)
        if self.is_approved(target):
            return target
        return None

    def list_approved(self) -> list[str]:
        return [str(d) for d in self.approved_directories]

    def get_active_directory(self) -> str:
        return str(self.active_directory) if self.active_directory else ""