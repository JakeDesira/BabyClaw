from pathlib import Path


class PlanExecutor:
    def __init__(self, memory=None, executor=None, filesystem_guard=None, response_generator=None, debug: bool = True):
        self.memory = memory
        self.executor = executor
        self.filesystem_guard = filesystem_guard
        self.response_generator = response_generator
        self.debug = debug


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[PLAN EXECUTOR DEBUG] {label}: {value}")


    def _get_approved_directories(self) -> list[str]:
        if self.filesystem_guard is None:
            return []

        return self.filesystem_guard.list_approved()


    def _resolve_relative_path(self, path_value: str, must_exist: bool = False) -> str:
        path_value = path_value.strip()

        if not path_value:
            return path_value

        path = Path(path_value)

        if path.is_absolute():
            return path_value

        approved_dirs = self._get_approved_directories()

        if not approved_dirs:
            return path_value

        if must_exist:
            for approved_dir in approved_dirs:
                candidate = Path(approved_dir) / path_value

                if candidate.exists():
                    return str(candidate)

        return str(Path(approved_dirs[0]) / path_value)


    def _prepare_create_file_action(self, prompt: str, action_input: str) -> str:
        parts = action_input.split("::", 1)
        filepath = parts[0].strip()

        filepath = self._resolve_relative_path(filepath)

        if self.response_generator is None:
            raise ValueError("ResponseGenerator is required for create_file actions.")

        generated = self.response_generator.generate_file_content(
            f"{prompt}\n\n"
            f"Target file path: {filepath}\n"
            f"Target file name: {Path(filepath).name}\n"
            f"Target file extension: {Path(filepath).suffix.lower()}"
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
        parts = action_input.split("::", 1)

        if len(parts) != 2:
            return action_input

        source_path, destination_path = parts

        source_path = self._resolve_relative_path(source_path, must_exist=True)
        destination_path = self._resolve_relative_path(destination_path)

        return f"{source_path}::{destination_path}"


    def _prepare_rename_action(self, action_input: str) -> str:
        parts = action_input.split("::", 1)

        if len(parts) != 2:
            return action_input

        source_path, new_name = parts

        source_path = self._resolve_relative_path(source_path, must_exist=True)

        return f"{source_path}::{new_name.strip()}"


    def _prepare_action_input(self, prompt: str, action: str, action_input: str) -> str:
        if action in ("create_directory", "list_directory"):
            return self._resolve_relative_path(action_input)

        if action == "create_file":
            return self._prepare_create_file_action(prompt, action_input)

        if action in ("edit_file", "delete_file", "view_file", "append_file"):
            return self._prepare_existing_file_action(action_input)

        if action in ("move_path", "copy_path"):
            return self._prepare_move_action(action_input)

        if action == "rename_path":
            return self._prepare_rename_action(action_input)

        return action_input


    def _handle_edit_ready(self, step_result: str, prompt: str) -> str:
        _, filepath, instruction, existing_content = step_result.split("::", 3)

        if self.response_generator is None:
            return "No response generator is available for edit_file flow."

        improved = self.response_generator.improve_file_content(
            prompt=prompt,
            existing_content=existing_content,
            instruction=instruction,
        )

        write_input = f"{filepath}::{improved}"
        write_result = self.executor.handle("create_file", write_input, prompt)

        if write_result.startswith("File created:"):
            if self.memory is not None:
                self.memory.set_last_active_file(Path(filepath).name, improved)

            return write_result.replace("File created:", "File updated:")

        return write_result


    def _remember_created_file(self, action: str, resolved_input: str, step_result: str | None) -> None:
        if action != "create_file":
            return

        if not step_result:
            return

        if not step_result.startswith("File created:"):
            return


    def execute_plan_once(self, prompt: str, plan: dict) -> dict:
        self._debug("EXECUTE PROMPT", prompt)
        self._debug("EXECUTE PLAN", plan)

        context = ""
        execution_results = []
        error = ""

        if plan.get("needs_memory") and self.memory is not None:
            context = self.memory.handle(plan.get("memory_action", "NONE"))
            self._debug("MEMORY CONTEXT", context)

        if plan.get("needs_executor") and self.executor is not None:
            actions = plan.get("executor_actions", [])

            for item in actions:
                action = item.get("action", "").strip()
                action_input = item.get("input", "")

                try:
                    resolved_input = self._prepare_action_input(prompt, action, action_input)
                except Exception as e:
                    error = f"Error preparing action input for '{action}': {e}"
                    execution_results.append(error)
                    break

                self._debug("ABOUT TO EXECUTE ACTION", action)
                self._debug("ABOUT TO EXECUTE INPUT", resolved_input)

                step_result = self.executor.handle(action, resolved_input, prompt)

                if step_result is None:
                    step_result = f"Error: Executor action '{action}' returned no result."

                self._remember_created_file(action, resolved_input, step_result)

                if step_result.startswith("EDIT_READY::"):
                    step_result = self._handle_edit_ready(step_result, prompt)

                self._debug("EXECUTOR ACTION", action)
                self._debug("EXECUTOR INPUT", resolved_input)
                self._debug("EXECUTION RESULT", step_result)

                execution_results.append(step_result)

                if step_result.startswith("Error") or step_result.startswith("Access denied"):
                    error = step_result
                    break

        execution_result = "\n".join(execution_results).strip()

        source_text = ""

        if self.response_generator is not None:
            source_text = self.response_generator.build_source_text(plan, context, execution_result)

        result = {
            "ok": error == "",
            "context": context,
            "execution_result": execution_result,
            "source_text": source_text,
            "error": error,
        }

        self._debug("PLAN EXECUTION OUTPUT", result)
        return result