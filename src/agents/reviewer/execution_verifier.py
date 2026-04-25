from pathlib import Path


class ExecutionVerifier:
    def __init__(self, filesystem_guard=None, debug: bool = True):
        self.filesystem_guard = filesystem_guard
        self.debug = debug


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[EXECUTION VERIFIER DEBUG] {label}: {value}")


    def _split_pair(self, text: str) -> tuple[str, str] | None:
        if "::" not in text:
            return None

        left, right = text.split("::", 1)
        return left.strip(), right


    def _resolve_safe_path(self, path_text: str) -> Path | None:
        if self.filesystem_guard is None:
            return None

        return self.filesystem_guard.safe_path(path_text)


    def verify_action(self, action: str, resolved_input: str, step_result: str) -> dict:
        """
        Verifies the real filesystem outcome after one executor action.

        Returns:
        {
            "ok": bool,
            "feedback": str
        }
        """

        if step_result.startswith("Error") or step_result.startswith("Access denied"):
            return {
                "ok": False,
                "feedback": step_result,
            }

        if action == "create_file":
            return self._verify_create_file(resolved_input)

        if action == "write_file":
            return self._verify_write_file(resolved_input)

        if action == "append_file":
            return self._verify_append_file(resolved_input)

        if action == "create_directory":
            return self._verify_create_directory(resolved_input)

        if action == "delete_file":
            return self._verify_delete_file(resolved_input)

        if action == "move_path":
            return self._verify_move_path(resolved_input)

        if action == "copy_path":
            return self._verify_copy_path(resolved_input)

        if action == "rename_path":
            return self._verify_rename_path(resolved_input)

        if action == "edit_file":
            # edit_file itself only prepares the edit.
            # The real write happens later through write_file.
            return {
                "ok": True,
                "feedback": "Edit preparation completed.",
            }

        return {
            "ok": True,
            "feedback": "No filesystem verification required for this action.",
        }


    def _verify_create_file(self, resolved_input: str) -> dict:
        parts = self._split_pair(resolved_input)

        if parts is None:
            return {
                "ok": False,
                "feedback": "Verification failed: expected filepath::content format.",
            }

        filepath, content = parts
        safe = self._resolve_safe_path(filepath)

        if safe is None:
            return {
                "ok": False,
                "feedback": f"Created file path is not approved: {filepath}",
            }

        if not safe.exists() or not safe.is_file():
            return {
                "ok": False,
                "feedback": f"Expected file was not created: {safe}",
            }

        try:
            actual_content = safe.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "ok": False,
                "feedback": f"Could not read created file for verification: {e}",
            }

        if actual_content != content:
            return {
                "ok": False,
                "feedback": f"Created file content does not match expected content: {safe}",
            }

        return {
            "ok": True,
            "feedback": f"Verified created file: {safe}",
        }


    def _verify_write_file(self, resolved_input: str) -> dict:
        parts = self._split_pair(resolved_input)

        if parts is None:
            return {
                "ok": False,
                "feedback": "Verification failed: expected filepath::content format.",
            }

        filepath, content = parts
        safe = self._resolve_safe_path(filepath)

        if safe is None:
            return {
                "ok": False,
                "feedback": f"Written file path is not approved: {filepath}",
            }

        if not safe.exists() or not safe.is_file():
            return {
                "ok": False,
                "feedback": f"Expected file was not written: {safe}",
            }

        try:
            actual_content = safe.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "ok": False,
                "feedback": f"Could not read written file for verification: {e}",
            }

        if actual_content != content:
            return {
                "ok": False,
                "feedback": f"Written file content does not match expected content: {safe}",
            }

        return {
            "ok": True,
            "feedback": f"Verified written file: {safe}",
        }


    def _verify_append_file(self, resolved_input: str) -> dict:
        parts = self._split_pair(resolved_input)

        if parts is None:
            return {
                "ok": False,
                "feedback": "Verification failed: expected filepath::content format.",
            }

        filepath, content = parts
        safe = self._resolve_safe_path(filepath)

        if safe is None:
            return {
                "ok": False,
                "feedback": f"Appended file path is not approved: {filepath}",
            }

        if not safe.exists() or not safe.is_file():
            return {
                "ok": False,
                "feedback": f"Expected appended file does not exist: {safe}",
            }

        try:
            actual_content = safe.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "ok": False,
                "feedback": f"Could not read appended file for verification: {e}",
            }

        if not actual_content.endswith(content):
            return {
                "ok": False,
                "feedback": f"Appended content was not found at the end of file: {safe}",
            }

        return {
            "ok": True,
            "feedback": f"Verified appended file: {safe}",
        }


    def _verify_delete_file(self, resolved_input: str) -> dict:
        safe = self._resolve_safe_path(resolved_input)

        if safe is None:
            return {
                "ok": False,
                "feedback": f"Deleted file path is not approved: {resolved_input}",
            }

        if safe.exists():
            return {
                "ok": False,
                "feedback": f"Expected file to be deleted, but it still exists: {safe}",
            }

        return {
            "ok": True,
            "feedback": f"Verified deleted file: {safe}",
        }
    

    def _verify_create_directory(self, resolved_input: str) -> dict:
        safe = self._resolve_safe_path(resolved_input)

        if safe is None:
            return {
                "ok": False,
                "feedback": f"Created directory path is not approved: {resolved_input}",
            }

        if not safe.exists() or not safe.is_dir():
            return {
                "ok": False,
                "feedback": f"Expected directory was not created: {safe}",
            }

        return {
            "ok": True,
            "feedback": f"Verified created directory: {safe}",
        }


    def _verify_move_path(self, resolved_input: str) -> dict:
        parts = self._split_pair(resolved_input)

        if parts is None:
            return {
                "ok": False,
                "feedback": "Verification failed: expected source_path::destination_path format.",
            }

        source_text, destination_text = parts

        source = self._resolve_safe_path(source_text)
        destination = self._resolve_safe_path(destination_text)

        if source is None or destination is None:
            return {
                "ok": False,
                "feedback": "Move source or destination is not approved.",
            }

        if source == destination:
            return {
                "ok": False,
                "feedback": "Move verification failed: source and destination are the same.",
            }

        if source.exists():
            return {
                "ok": False,
                "feedback": f"Move source still exists after move: {source}",
            }

        if not destination.exists():
            return {
                "ok": False,
                "feedback": f"Move destination does not exist: {destination}",
            }

        return {
            "ok": True,
            "feedback": f"Verified move: {source} -> {destination}",
        }


    def _verify_copy_path(self, resolved_input: str) -> dict:
        parts = self._split_pair(resolved_input)

        if parts is None:
            return {
                "ok": False,
                "feedback": "Verification failed: expected source_path::destination_path format.",
            }

        source_text, destination_text = parts

        source = self._resolve_safe_path(source_text)
        destination = self._resolve_safe_path(destination_text)

        if source is None or destination is None:
            return {
                "ok": False,
                "feedback": "Copy source or destination is not approved.",
            }

        if not source.exists():
            return {
                "ok": False,
                "feedback": f"Copy source does not exist: {source}",
            }

        if not destination.exists():
            return {
                "ok": False,
                "feedback": f"Copy destination does not exist: {destination}",
            }

        return {
            "ok": True,
            "feedback": f"Verified copy: {source} -> {destination}",
        }


    def _verify_rename_path(self, resolved_input: str) -> dict:
        parts = self._split_pair(resolved_input)

        if parts is None:
            return {
                "ok": False,
                "feedback": "Verification failed: expected source_path::new_name format.",
            }

        source_text, new_name = parts
        new_name = new_name.strip()

        source = self._resolve_safe_path(source_text)

        if source is None:
            return {
                "ok": False,
                "feedback": f"Rename source is not approved: {source_text}",
            }

        if source.name == new_name:
            return {
                "ok": False,
                "feedback": "Rename verification failed: new name is the same as the old name.",
            }

        destination = source.with_name(new_name)

        if source.exists():
            return {
                "ok": False,
                "feedback": f"Rename source still exists after rename: {source}",
            }

        if not destination.exists():
            return {
                "ok": False,
                "feedback": f"Rename destination does not exist: {destination}",
            }

        return {
            "ok": True,
            "feedback": f"Verified rename: {source} -> {destination}",
        }