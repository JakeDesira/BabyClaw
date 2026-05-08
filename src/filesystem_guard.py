from pathlib import Path


class FilesystemGuard:
    """Track approved directories and resolve safe filesystem paths."""
    def __init__(self):
        """Initialise the instance."""
        self.approved_directories: list[Path] = []
        self.active_directory: Path | None = None


    def request_approval(self, raw_path: str) -> str:
        """Build the user-facing approval request for a directory."""
        resolved = Path(raw_path).expanduser().resolve()

        return (
            f"The agent is requesting access to:\n"
            f"  {resolved}\n\n"
            f"Type YES to approve or NO to deny."
        )
    
    def set_active_directory(self, raw_path: str | Path) -> bool:
        """Set the active directory if it sits inside any approved root."""
        resolved = Path(raw_path).expanduser().resolve()

        if not resolved.exists() or not resolved.is_dir():
            return False

        if not self._is_inside_any_approved(resolved):
            return False

        self.active_directory = resolved
        return True


    def approve(self, raw_path: str) -> bool:
        """Approve a directory and make it active.

        The new path is treated as an active workspace if it is already covered
        by an existing approved root. If it is broader than (or unrelated to)
        every existing approved root, narrower descendants are pruned and the
        new path becomes an approved root.
        """
        resolved = Path(raw_path).expanduser().resolve()

        if not resolved.exists() or not resolved.is_dir():
            return False

        for approved in self.approved_directories:
            if resolved == approved or approved in resolved.parents:
                self.active_directory = resolved
                return True

        self.approved_directories = [
            approved
            for approved in self.approved_directories
            if resolved not in approved.parents
        ]

        self.approved_directories.append(resolved)
        self.active_directory = resolved

        return True


    def _is_inside_any_approved(self, path: Path) -> bool:
        """Return whether a resolved path equals or is inside any approved root."""
        return any(
            path == approved or approved in path.parents
            for approved in self.approved_directories
        )


    def resolve_path(self, file_path: str | Path) -> Path:
        """Resolve a path relative to the active directory when needed."""
        raw = Path(file_path).expanduser()

        if not raw.is_absolute() and self.active_directory is not None:
            raw = self.active_directory / raw

        return raw.resolve()


    def is_approved(self, file_path: str | Path) -> bool:
        """Return whether a path is inside an approved directory."""
        target = self.resolve_path(file_path)

        return any(
            target == approved or approved in target.parents
            for approved in self.approved_directories
        )


    def safe_path(self, path: str | Path) -> Path | None:
        """Return a resolved path only when it is approved."""
        raw_path = Path(str(path).strip().strip("\"'")).expanduser()

        if raw_path.is_absolute():
            candidate = raw_path.resolve()
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
        """Return approved directory roots as a list of resolved string paths."""
        return [str(directory) for directory in self.approved_directories]


    def get_active_directory(self) -> str:
        """Return the active directory as a string, or an empty string if unset."""
        if self.active_directory is None:
            return ""

        return str(self.active_directory)


    def revoke(self, raw_path: str) -> bool:
        """Remove a directory from the approved set."""
        resolved = Path(raw_path).expanduser().resolve()

        before_count = len(self.approved_directories)

        self.approved_directories = [
            directory
            for directory in self.approved_directories
            if directory.resolve() != resolved
        ]

        if self.active_directory is not None and not self._is_inside_any_approved(self.active_directory):
            self.active_directory = (
                self.approved_directories[-1]
                if self.approved_directories
                else None
            )

        return len(self.approved_directories) < before_count


    def get_approved_root_for_path(self, file_path: str | Path) -> Path | None:
        """Return the most specific approved root that contains ``file_path``."""
        target = self.resolve_path(file_path)

        matching_roots = [
            approved
            for approved in self.approved_directories
            if target == approved or approved in target.parents
        ]

        if not matching_roots:
            return None

        return max(matching_roots, key=lambda path: len(path.parts))
