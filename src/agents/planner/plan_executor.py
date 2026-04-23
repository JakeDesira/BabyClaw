from pathlib import Path


class PlanExecutor:
    def __init__(self,memory=None, executor=None, filesystem_guard=None, response_generator=None, debug: bool = True):
        self.memory = memory
        self.executor = executor
        self.filesystem_guard = filesystem_guard
        self.response_generator = response_generator
        self.debug = debug

    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[PLAN EXECUTOR DEBUG] {label}: {value}")

    def _prepare_action_input(self, prompt: str, action: str, action_input: str) -> str:
        if action in ("create_directory", "list_directory"):
            path_value = action_input.strip()

            if not Path(path_value).is_absolute() and self.filesystem_guard:
                dirs = self.filesystem_guard.list_approved()
                if dirs:
                    path_value = str(Path(dirs[0]) / path_value)

            return path_value

        if action == "create_file":
            parts = action_input.split("::", 1)
            filepath = parts[0].strip()

            if not Path(filepath).is_absolute() and self.filesystem_guard:
                dirs = self.filesystem_guard.list_approved()
                if dirs:
                    filepath = str(Path(dirs[0]) / filepath)

            if self.response_generator is None:
                raise ValueError("ResponseGenerator is required for create_file actions.")

            generated = self.response_generator.generate_file_content(
                f"{prompt}\n\nTarget file path: {filepath}\nTarget file name: {Path(filepath).name}\nTarget file extension: {Path(filepath).suffix.lower()}"
            )

            return f"{filepath}::{generated}"

        if action in ("edit_file", "delete_file", "view_file", "append_file"):
            parts = action_input.split("::", 1)
            filepath = parts[0].strip()
            rest = parts[1] if len(parts) > 1 else ""

            if not Path(filepath).is_absolute() and self.filesystem_guard:
                for approved_dir in self.filesystem_guard.list_approved():
                    candidate = Path(approved_dir) / filepath
                    if candidate.exists():
                        filepath = str(candidate)
                        break
                else:
                    dirs = self.filesystem_guard.list_approved()
                    if dirs:
                        filepath = str(Path(dirs[0]) / filepath)

            return f"{filepath}::{rest}" if rest else filepath

        if action == "move_path":
            parts = action_input.split("::", 1)
            if len(parts) != 2:
                return action_input

            source_path, destination_path = parts
            source_path = source_path.strip()
            destination_path = destination_path.strip()

            if self.filesystem_guard:
                dirs = self.filesystem_guard.list_approved()

                if not Path(source_path).is_absolute() and dirs:
                    source_path = str(Path(dirs[0]) / source_path)

                if not Path(destination_path).is_absolute() and dirs:
                    destination_path = str(Path(dirs[0]) / destination_path)

            return f"{source_path}::{destination_path}"

        if action == "rename_path":
            parts = action_input.split("::", 1)
            if len(parts) != 2:
                return action_input

            source_path, new_name = parts
            source_path = source_path.strip()
            new_name = new_name.strip()

            if self.filesystem_guard:
                dirs = self.filesystem_guard.list_approved()
                if not Path(source_path).is_absolute() and dirs:
                    source_path = str(Path(dirs[0]) / source_path)

            return f"{source_path}::{new_name}"

        return action_input

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
                step_result = self.executor.handle(action, resolved_input, prompt)

                if action == "create_file" and step_result.startswith("File created:") and self.memory is not None:
                    parts = resolved_input.split("::", 1)
                    if len(parts) == 2:
                        filepath, content = parts
                        self.memory.set_last_active_file(Path(filepath).name, content)

                if step_result.startswith("EDIT_READY::"):
                    _, filepath, instruction, existing_content = step_result.split("::", 3)

                    if self.response_generator is None:
                        error = "No response generator is available for edit_file flow."
                        execution_results.append(error)
                        break

                    improved = self.response_generator.improve_file_content(
                        prompt=prompt,
                        existing_content=existing_content,
                        instruction=instruction,
                    )

                    write_input = f"{filepath}::{improved}"
                    write_result = self.executor.handle("create_file", write_input, prompt)

                    if write_result.startswith("File created:"):
                        step_result = write_result.replace("File created:", "File updated:")
                        if self.memory is not None:
                            self.memory.set_last_active_file(Path(filepath).name, improved)
                    else:
                        step_result = write_result

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