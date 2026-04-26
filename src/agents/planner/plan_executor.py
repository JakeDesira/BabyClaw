from pathlib import Path


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


QUIET_ACTIONS = {
    "read_file",
    "view_file",
}


class PlanExecutor:
    def __init__(self, memory=None, executor=None, filesystem_guard=None, response_generator=None, execution_verifier=None, transaction_manager=None, debug: bool = True):
        self.memory = memory
        self.executor = executor
        self.filesystem_guard = filesystem_guard
        self.response_generator = response_generator
        self.execution_verifier = execution_verifier
        self.transaction_manager = transaction_manager
        self._last_write_input = ""
        self.debug = debug


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[PLAN EXECUTOR DEBUG] {label}: {value}")


    def _get_approved_directories(self) -> list[str]:
        if self.filesystem_guard is None:
            return []

        return self.filesystem_guard.list_approved()

    # ===== Directory/Path Helpers =====
    def _find_first_matching_path(self, root: Path, file_name: str) -> Path | None:
        skip_dirs = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            ".mypy_cache",
            ".pytest_cache",
            ".idea",
            ".vscode",
        }

        try:
            for candidate in root.rglob(file_name):
                if any(part in skip_dirs for part in candidate.parts):
                    continue

                if candidate.exists():
                    return candidate

        except Exception:
            return None

        return None


    def _resolve_relative_path(self, path_value: str, must_exist: bool = False) -> str:
        path_value = path_value.strip().strip("'\"")

        if not path_value:
            return path_value

        path_value = path_value.replace("\\", "/")
        path = Path(path_value).expanduser()

        if path.is_absolute():
            return str(path)

        approved_dirs = self._get_approved_directories()

        if not approved_dirs:
            return path_value

        path_parts = path.parts
        first_part = path_parts[0].lower() if path_parts else ""

        # 1. If the user explicitly names an approved directory, use that directory.
        for approved_dir in approved_dirs:
            approved_path = Path(approved_dir)
            approved_name = approved_path.name.lower()

            if first_part == approved_name:
                remaining_path = Path(*path_parts[1:]) if len(path_parts) > 1 else Path()
                candidate = approved_path / remaining_path

                if must_exist:
                    if candidate.exists():
                        return str(candidate)

                    match = self._find_first_matching_path(approved_path, path.name)

                    if match is not None:
                        return str(match)

                return str(candidate)

        # 2. Otherwise, use the active directory, not the latest approved directory.
        active_directory = ""

        if self.filesystem_guard is not None:
            try:
                active_directory = self.filesystem_guard.get_active_directory()
            except AttributeError:
                active_directory = ""

        if active_directory:
            base_dir = Path(active_directory)
        else:
            base_dir = Path(approved_dirs[-1])

        candidate = base_dir / path

        if must_exist:
            if candidate.exists():
                return str(candidate)

            # Important:
            # Search only inside the active/base directory.
            # Do not search all approved directories.
            match = self._find_first_matching_path(base_dir, path.name)

            if match is not None:
                return str(match)

        return str(candidate)


    def _get_snapshot_directory_for_plan(self, prompt: str, plan: dict) -> str:
        approved_dirs = self._get_approved_directories()

        if not approved_dirs:
            return ""

        for item in plan.get("executor_actions", []):
            action = item.get("action", "").strip()
            action_input = item.get("input", "")

            snapshot_directory = self.get_snapshot_directory_for_action(
                prompt,
                action,
                action_input,
            )

            if snapshot_directory:
                return snapshot_directory

        return approved_dirs[-1]
    

    def get_snapshot_directory_for_action(self, prompt: str, action: str, action_input: str) -> str:
        approved_dirs = self._get_approved_directories()

        if not approved_dirs:
            return ""

        if action not in {
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
        }:
            return ""

        try:
            resolved_input = self._prepare_action_input(
                prompt,
                action,
                action_input,
                previous_results=[],
            )
        except Exception:
            return approved_dirs[-1]

        if action in {"move_path", "move_directory_contents", "copy_path"} and "::" in resolved_input:
            source_part, destination_part = resolved_input.split("::", 1)

            if action == "move_directory_contents":
                path_part = source_part.strip()
            else:
                path_part = destination_part.strip()
        else:
            path_part = resolved_input.split("::", 1)[0].strip()

        if not path_part:
            return approved_dirs[-1]

        path = Path(path_part).expanduser().resolve()

        if action == "create_directory":
            affected_path = path
        elif path.suffix:
            affected_path = path.parent
        else:
            affected_path = path

        if self.filesystem_guard is not None:
            try:
                approved_root = self.filesystem_guard.get_approved_root_for_path(affected_path)

                if approved_root is not None:
                    return str(approved_root)
            except AttributeError:
                pass

        return str(affected_path)


    # ==== Action Preparation Helpers =====
    def _prepare_create_file_action(self, prompt: str, action_input: str, previous_results: list[str] | None = None) -> str:
        parts = action_input.split("::", 1)
        filepath = parts[0].strip()
        filepath = self._resolve_relative_path(filepath)

        if len(parts) == 2:
            content = parts[1]
            return f"{filepath}::{content}"

        if self.response_generator is None:
            raise ValueError("ResponseGenerator is required for create_file actions.")

        execution_context = "\n\n".join(previous_results or [])

        generated = self.response_generator.generate_file_content(
            f"{prompt}\n\n"
            f"Target file path: {filepath}\n"
            f"Target file name: {Path(filepath).name}\n"
            f"Target file extension: {Path(filepath).suffix.lower()}",
            execution_context=execution_context,
        )

        return f"{filepath}::{generated}"


    def _prepare_existing_file_action(self, action_input: str) -> str:
        parts = action_input.split("::", 1)
        filepath = parts[0].strip()
        rest = parts[1] if len(parts) > 1 else ""

        filepath = self._resolve_relative_path(filepath, must_exist=True)

        if rest:
            return f"{filepath}::{rest}"

        return filepath


    def _prepare_move_action(self, action_input: str) -> str:
        cleaned_input = action_input.strip().strip("'\"")

        if "::" in cleaned_input:
            source_path, destination_path = cleaned_input.split("::", 1)
        elif ":" in cleaned_input:
            # Repair common planner mistake:
            # source:destination -> source::destination
            source_path, destination_path = cleaned_input.split(":", 1)
        else:
            return cleaned_input

        source_path = self._resolve_relative_path(source_path.strip(), must_exist=True)
        destination_path = self._resolve_relative_path(destination_path.strip())

        return f"{source_path}::{destination_path}"


    def _prepare_rename_action(self, action_input: str) -> str:
        parts = action_input.split("::", 1)

        if len(parts) != 2:
            return action_input

        source_path, new_name = parts

        source_path = self._resolve_relative_path(source_path, must_exist=True)

        return f"{source_path}::{new_name.strip()}"


    def _prepare_action_input(self, prompt: str, action: str, action_input: str, previous_results: list[str] | None = None) -> str:
        if action == "create_directory":
            return self._resolve_relative_path(action_input)

        if action == "list_directory":
            if not action_input.strip():
                approved_dirs = self._get_approved_directories()

                if approved_dirs:
                    return approved_dirs[-1]

            return self._resolve_relative_path(action_input)

        if action == "find_file":
            return action_input

        if action == "create_file":
            return self._prepare_create_file_action(prompt, action_input, previous_results)

        if action in ("edit_file", "delete_file", "view_file", "append_file", "write_file", "run_python_file"):
            return self._prepare_existing_file_action(action_input)

        if action in ("move_path", "move_directory_contents", "copy_path"):
            return self._prepare_move_action(action_input)

        if action == "rename_path":
            return self._prepare_rename_action(action_input)

        return action_input


    # ===== Edit/Memory Helpers =====
    def _handle_edit_ready(self, step_result: str, prompt: str) -> str:
        _, filepath, instruction, existing_content = step_result.split("::", 3)

        if self.response_generator is None:
            return "No response generator is available for edit_file flow."

        improved = self.response_generator.improve_file_content(
            prompt=f"{prompt}\n\nTarget file: {filepath}",
            existing_content=existing_content,
            instruction=instruction,
        )

        write_input = f"{filepath}::{improved}"
        self._last_write_input = write_input

        write_result = self.executor.handle("write_file", write_input, prompt)

        if write_result.startswith("File updated:"):
            if self.memory is not None:
                self.memory.set_last_active_file(Path(filepath).name, improved)

        return write_result


    def _remember_created_file(self, action: str, resolved_input: str, step_result: str | None) -> None:
        if action != "create_file":
            return

        if self.memory is None:
            return

        if not step_result or not step_result.startswith("File created:"):
            return

        parts = resolved_input.split("::", 1)

        if len(parts) != 2:
            return

        filepath, content = parts
        self.memory.set_last_active_file(Path(filepath).name, content)


    # ===== Execution Methods =====
    def _plan_has_write_actions(self, plan: dict) -> bool:
        return any(
            item.get("action") in WRITE_ACTIONS
            for item in plan.get("executor_actions", [])
        )
    

    def _get_snapshot_metadata(self) -> dict:
        if self.transaction_manager is None:
            return {
                "snapshot_path": "",
                "snapshot_target": "",
            }

        try:
            return {
                "snapshot_path": self.transaction_manager.get_last_snapshot_path(),
                "snapshot_target": self.transaction_manager.get_last_target_path(),
            }
        except AttributeError:
            return {
                "snapshot_path": "",
                "snapshot_target": "",
            }
        

    def _execute_prepared_action(self, prompt: str, action: str, action_input: str, resolved_input: str) -> dict:
        step_result = self.executor.handle(action, resolved_input, prompt)

        if step_result is None:
            step_result = f"Error: Executor action '{action}' returned no result."

        verification_result = None

        if step_result.startswith("EDIT_READY::"):
            step_result = self._handle_edit_ready(step_result, prompt)

            if self.execution_verifier is not None and step_result.startswith("File updated:"):
                verification_result = self.execution_verifier.verify_action(
                    "write_file",
                    self._last_write_input,
                    step_result,
                )
        else:
            if self.execution_verifier is not None:
                verification_result = self.execution_verifier.verify_action(
                    action,
                    resolved_input,
                    step_result,
                )

        self._remember_created_file(action, resolved_input, step_result)

        ok = not (
            step_result.startswith("Error")
            or step_result.startswith("Access denied")
            or (
                verification_result is not None
                and not verification_result.get("ok", False)
            )
        )

        return {
            "ok": ok,
            "action": action,
            "input": action_input,
            "resolved_input": resolved_input,
            "result": step_result,
            "verification": verification_result,
        }


    def execute_plan_once(self, prompt: str, plan: dict) -> dict:
        self._debug("EXECUTE PROMPT", prompt)
        self._debug("EXECUTE PLAN", plan)

        context = ""
        execution_results = []
        user_visible_results = []
        error = ""
        snapshot_result = ""
        steps_trace = []

        if self.transaction_manager is not None and self._plan_has_write_actions(plan):
            snapshot_directory = self._get_snapshot_directory_for_plan(prompt, plan)

            if snapshot_directory:
                snapshot_result = self.transaction_manager.snapshot_directory(snapshot_directory)
            else:
                snapshot_result = self.transaction_manager.snapshot_active_directory()

            self._debug("SNAPSHOT DIRECTORY", snapshot_directory)
            self._debug("SNAPSHOT RESULT", snapshot_result)

            if snapshot_result.startswith("Error"):
                snapshot_metadata = self._get_snapshot_metadata()

                return {
                    "ok": False,
                    "context": "",
                    "execution_result": snapshot_result,
                    "full_execution_result": snapshot_result,
                    "source_text": snapshot_result,
                    "error": snapshot_result,
                    "steps": [],
                    "snapshot_result": snapshot_result,
                    "snapshot_path": snapshot_metadata["snapshot_path"],
                    "snapshot_target": snapshot_metadata["snapshot_target"],
                }

        if plan.get("needs_memory") and self.memory is not None:
            context = self.memory.handle(
                plan.get("memory_action", "NONE"),
                plan.get("memory_input", ""),
            )
            self._debug("MEMORY CONTEXT", context)

        if plan.get("needs_executor") and self.executor is not None:
            actions = plan.get("executor_actions", [])

            for item in actions:
                action = item.get("action", "").strip()
                action_input = item.get("input", "")

                try:
                    resolved_input = self._prepare_action_input(
                        prompt,
                        action,
                        action_input,
                        previous_results=execution_results,
                    )
                except Exception as e:
                    error = f"Error preparing action input for '{action}': {e}"
                    execution_results.append(error)
                    user_visible_results.append(error)
                    break

                self._debug("ABOUT TO EXECUTE ACTION", action)
                self._debug("ABOUT TO EXECUTE INPUT", resolved_input)

                step_data = self._execute_prepared_action(
                    prompt=prompt,
                    action=action,
                    action_input=action_input,
                    resolved_input=resolved_input,
                )

                step_result = step_data["result"]
                verification_result = step_data["verification"]

                steps_trace.append(step_data)

                self._debug("EXECUTOR ACTION", action)
                self._debug("EXECUTOR INPUT", resolved_input)
                self._debug("EXECUTION RESULT", step_result)
                self._debug("VERIFICATION RESULT", verification_result)

                execution_results.append(step_result)

                if verification_result is not None and not verification_result.get("ok", False):
                    error = verification_result.get("feedback", "Verification failed.")
                    execution_results.append(error)
                    user_visible_results.append(error)

                    if self.transaction_manager is not None:
                        rollback_result = self.transaction_manager.rollback_last_snapshot()
                        execution_results.append(rollback_result)
                        user_visible_results.append(rollback_result)

                    break

                if step_result.startswith("Error") or step_result.startswith("Access denied"):
                    error = step_result
                    user_visible_results.append(step_result)
                    break

                if action not in QUIET_ACTIONS or len(actions) == 1:
                    user_visible_results.append(step_result)

        execution_result = "\n".join(user_visible_results).strip()
        full_execution_result = "\n\n".join(execution_results).strip()

        source_text = ""

        if self.response_generator is not None:
            source_text = self.response_generator.build_source_text(
                plan,
                context,
                full_execution_result,
            )

        snapshot_metadata = self._get_snapshot_metadata()

        result = {
            "ok": error == "",
            "context": context,
            "execution_result": execution_result,
            "full_execution_result": full_execution_result,
            "source_text": source_text,
            "error": error,
            "steps": steps_trace,
            "snapshot_result": snapshot_result,
            "snapshot_path": snapshot_metadata["snapshot_path"],
            "snapshot_target": snapshot_metadata["snapshot_target"],
        }

        self._debug("PLAN EXECUTION OUTPUT", result)
        return result
    

    def execute_single_action(self, prompt: str, action: str, action_input: str, previous_results: list[str] | None = None) -> dict:
        if self.executor is None:
            return {
                "ok": False,
                "action": action,
                "input": action_input,
                "resolved_input": "",
                "result": "Error: Executor is not available.",
                "verification": None,
            }

        try:
            resolved_input = self._prepare_action_input(
                prompt,
                action,
                action_input,
                previous_results=previous_results or [],
            )
        except Exception as e:
            return {
                "ok": False,
                "action": action,
                "input": action_input,
                "resolved_input": "",
                "result": f"Error preparing action input for '{action}': {e}",
                "verification": None,
            }

        return self._execute_prepared_action(
            prompt=prompt,
            action=action,
            action_input=action_input,
            resolved_input=resolved_input,
        )