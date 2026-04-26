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
    
    def set_active_directory(self, raw_path: str | Path) -> bool:
        resolved = Path(raw_path).expanduser().resolve()

        if resolved not in self.approved_directories:
            return False

        if not resolved.exists() or not resolved.is_dir():
            return False

        self.active_directory = resolved
        return True


    def approve(self, raw_path: str) -> bool:
        resolved = Path(raw_path).expanduser().resolve()

        if not resolved.exists() or not resolved.is_dir():
            return False

        for approved in self.approved_directories:
            if resolved == approved:
                self.active_directory = approved
                return True

            if resolved in approved.parents:
                self.active_directory = approved
                return True

        self.approved_directories = [
            approved
            for approved in self.approved_directories
            if approved not in resolved.parents
        ]

        self.approved_directories.append(resolved)
        self.active_directory = resolved

        return True


    def resolve_path(self, file_path: str | Path) -> Path:
        raw = Path(file_path).expanduser()

        if not raw.is_absolute() and self.active_directory is not None:
            raw = self.active_directory / raw

        return raw.resolve()


    def is_approved(self, file_path: str | Path) -> bool:
        target = self.resolve_path(file_path)

        return any(
            target == approved or approved in target.parents
            for approved in self.approved_directories
        )


    def safe_path(self, path: str | Path) -> Path | None:
        raw_path = Path(str(path).strip().strip("\"'"))

        if raw_path.is_absolute():
            candidate = raw_path.expanduser().resolve()
        else:
            active_directory = self.get_active_directory()

            if not active_directory:
                return None

            candidate = (Path(active_directory) / raw_path).expanduser().resolve()

        for approved_path in self.approved_directories:
            approved = Path(approved_path).expanduser().resolve()

            try:
                candidate.relative_to(approved)
                return candidate
            except ValueError:
                continue

        return None


    def list_approved(self) -> list[str]:
        return [str(directory) for directory in self.approved_directories]


    def get_active_directory(self) -> str:
        if self.active_directory is None:
            return ""

        return str(self.active_directory)


    def revoke(self, raw_path: str) -> bool:
        resolved = Path(raw_path).expanduser().resolve()

        before_count = len(self.approved_directories)

        self.approved_directories = [
            directory
            for directory in self.approved_directories
            if directory.resolve() != resolved
        ]

        if self.active_directory is not None and self.active_directory.resolve() == resolved:
            self.active_directory = (
                self.approved_directories[-1]
                if self.approved_directories
                else None
            )

        return len(self.approved_directories) < before_count


    def get_approved_root_for_path(self, file_path: str | Path) -> Path | None:
        target = self.resolve_path(file_path)

        matching_roots = [
            approved
            for approved in self.approved_directories
            if target == approved or approved in target.parents
        ]

        if not matching_roots:
            return None

        return max(matching_roots, key=lambda path: len(path.parts))