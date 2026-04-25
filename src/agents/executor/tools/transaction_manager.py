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
    "copy_path",
    "rename_path",
}


class TransactionManager:
    def __init__(self, filesystem_guard, snapshot_root: str | Path = ".babyclaw_snapshots"):
        self.filesystem_guard = filesystem_guard
        self.snapshot_root = Path(snapshot_root).resolve()
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

        self.last_snapshot_path: Path | None = None
        self.last_target_path: Path | None = None


    def has_write_actions(self, actions: list[dict]) -> bool:
        for item in actions:
            if item.get("action") in WRITE_ACTIONS:
                return True

        return False


    def snapshot_active_directory(self) -> str:
        active_directory = self.filesystem_guard.active_directory

        if active_directory is None:
            return "Error: No active approved directory to snapshot."

        active_directory = Path(active_directory).resolve()

        if not active_directory.exists() or not active_directory.is_dir():
            return f"Error: Active directory does not exist: {active_directory}"

        snapshot_id = uuid.uuid4().hex
        snapshot_path = self.snapshot_root / snapshot_id

        shutil.copytree(active_directory, snapshot_path)

        self.last_snapshot_path = snapshot_path
        self.last_target_path = active_directory

        return f"Snapshot created: {snapshot_path}"


    def rollback_last_snapshot(self) -> str:
        if self.last_snapshot_path is None or self.last_target_path is None:
            return "Nothing to undo. No snapshot is available."

        if not self.last_snapshot_path.exists():
            return "Undo failed. Snapshot no longer exists."

        target = self.last_target_path
        restore_temp = target.with_name(target.name + "_babyclaw_restore_temp")

        try:
            if restore_temp.exists():
                shutil.rmtree(restore_temp)

            shutil.copytree(self.last_snapshot_path, restore_temp)

            if target.exists():
                shutil.rmtree(target)

            restore_temp.rename(target)

            return f"Undo complete. Restored: {target}"

        except Exception as e:
            return f"Undo failed: {e}"


    def clear_last_snapshot(self) -> None:
        """
        Optional. You may choose not to delete snapshots immediately
        so the user can still type undo after a completed operation.
        """
        self.last_snapshot_path = None
        self.last_target_path = None