from pathlib import Path
import shutil
import uuid


WRITE_ACTIONS = {
    "create_file",
    "write_file",
    "append_file",
    "delete_file",
    "edit_file",
    "create_directory",
    "move_path",
    "move_directory_contents",
    "copy_path",
    "rename_path",
}


class TransactionManager:
    def __init__(self, filesystem_guard, snapshot_root: str | Path = ".babyclaw_snapshots"):
        self.filesystem_guard = filesystem_guard
        self.snapshot_root = Path(snapshot_root).expanduser().resolve()
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

        self.last_snapshot_path: Path | None = None
        self.last_target_path: Path | None = None


    def has_write_actions(self, actions: list[dict]) -> bool:
        return any(
            item.get("action") in WRITE_ACTIONS
            for item in actions
        )


    def get_last_snapshot_path(self) -> str:
        if self.last_snapshot_path is None:
            return ""

        return str(self.last_snapshot_path)


    def get_last_target_path(self) -> str:
        if self.last_target_path is None:
            return ""

        return str(self.last_target_path)


    def snapshot_active_directory(self) -> str:
        active_directory = self.filesystem_guard.active_directory

        if active_directory is None:
            return "Error: No active approved directory to snapshot."

        return self.snapshot_directory(active_directory)


    def snapshot_directory(self, directory_path: str | Path) -> str:
        directory = Path(directory_path).expanduser().resolve()

        if not directory.exists() or not directory.is_dir():
            return f"Error: Cannot snapshot non-directory path: {directory}"

        if not self.filesystem_guard.is_approved(directory):
            return f"Error: Cannot snapshot unapproved directory: {directory}"

        snapshot_path = self.snapshot_root / uuid.uuid4().hex

        try:
            shutil.copytree(directory, snapshot_path)

            self.last_snapshot_path = snapshot_path
            self.last_target_path = directory

            return f"Snapshot created: {snapshot_path}"

        except Exception as e:
            self.last_snapshot_path = None
            self.last_target_path = None

            return f"Error creating snapshot: {e}"


    def rollback_last_snapshot(self) -> str:
        if self.last_snapshot_path is None or self.last_target_path is None:
            return "Nothing to undo. No snapshot is available."

        snapshot_path = Path(self.last_snapshot_path)
        target_path = Path(self.last_target_path)

        if not snapshot_path.exists() or not snapshot_path.is_dir():
            return f"Nothing to undo. Snapshot folder was not found: {snapshot_path}"

        if not self.filesystem_guard.is_approved(target_path):
            return f"Undo failed: target directory is no longer approved: {target_path}"

        target_parent = target_path.parent
        token = uuid.uuid4().hex[:8]

        restore_temp = target_parent / f".{target_path.name}_restore_{token}"
        backup_path = target_parent / f".{target_path.name}_backup_{token}"

        try:
            if restore_temp.exists():
                shutil.rmtree(restore_temp, ignore_errors=True)

            shutil.copytree(snapshot_path, restore_temp)

            if target_path.exists():
                target_path.rename(backup_path)

            restore_temp.rename(target_path)

            if backup_path.exists():
                try:
                    shutil.rmtree(backup_path)
                except Exception as cleanup_error:
                    self.clear_last_snapshot()

                    return (
                        f"Undo complete. Restored: {target_path}\n\n"
                        f"Warning: backup cleanup failed: {backup_path}\n"
                        f"{cleanup_error}"
                    )

            self.clear_last_snapshot()

            return f"Undo complete. Restored: {target_path}"

        except Exception as e:
            if not target_path.exists() and backup_path.exists():
                try:
                    backup_path.rename(target_path)
                except Exception:
                    pass

            if restore_temp.exists():
                shutil.rmtree(restore_temp, ignore_errors=True)

            return (
                "Undo failed safely. The original folder was not intentionally deleted.\n\n"
                f"Error: {e}"
            )


    def clear_last_snapshot(self) -> None:
        self.last_snapshot_path = None
        self.last_target_path = None