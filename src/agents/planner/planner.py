from pathlib import Path
import re
import json

from ollama_client import OllamaClient
import prompts
import agents.executor.tools as tools


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


INSPECTION_ACTIONS = {
    "list_directory",
    "view_file",
    "read_file",
    "find_file",
}


SKIP_DIRECTORY_SUMMARY_DIRS = {
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


class PlannerAgent:
    def __init__(self, memory=None, planning_model: str | None = None, filesystem_guard=None, reasoning_settings=None, debug: bool = True):
        self.memory = memory
        self.debug = debug
        self.filesystem_guard = filesystem_guard
        self.reasoning_settings = reasoning_settings
        self.planning_client = OllamaClient(model=planning_model)

    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[PLANNER DEBUG] {label}: {value}")

    # ===== Context Helpers =====
    def _get_context(self) -> str:
        if self.memory is None:
            return ""

        try:
            return self.memory.get_short_term_context()
        except AttributeError:
            return ""
        
    def _get_approved_directories(self) -> list[str]:
        if self.filesystem_guard is None:
            return []
        
        return self.filesystem_guard.list_approved()
    

    def _summarise_directory_tree(self, root: Path, max_depth: int = 3, max_entries: int = 100) -> str:
        lines = []
        count = 0

        def walk(path: Path, depth: int) -> None:
            nonlocal count

            if depth > max_depth or count >= max_entries:
                return

            try:
                entries = sorted(path.iterdir(), key=lambda p: p.name.lower())
            except Exception:
                return

            for entry in entries:
                if count >= max_entries:
                    return

                try:
                    relative = entry.relative_to(root)
                except ValueError:
                    relative = entry

                kind = "[DIR]" if entry.is_dir() else "[FILE]"
                lines.append(f"{kind} {relative}")
                count += 1

                if entry.is_dir() and entry.name not in SKIP_DIRECTORY_SUMMARY_DIRS:
                    walk(entry, depth + 1)

        walk(root, 1)

        return "\n".join(lines) if lines else "(empty)"
    

    def _build_directory_context(self, approved_dirs: list[str]) -> str:
        if not approved_dirs:
            return ""

        directory_summaries = []

        for approved_dir in approved_dirs:
            try:
                path = Path(approved_dir)

                if path.exists() and path.is_dir():
                    summary = self._summarise_directory_tree(path)
                    directory_summaries.append(
                        f"Recursive contents of approved directory {approved_dir}:\n{summary}"
                    )
            except Exception as e:
                self._debug("DIRECTORY SUMMARY ERROR", f"{approved_dir}: {e}")

        return "\n\n".join(directory_summaries)
    
    
    def _build_file_state_context(self) -> str:
        if self.memory is None:
            return "No file currently active."

        last_file_name = self.memory.get_last_active_file_name()
        content = self.memory.get_last_active_file_content()

        if not last_file_name:
            return "No file currently active."

        preview = ""

        if content:
            preview = content[:300] + ("..." if len(content) > 300 else "")

        return (
            f"Last active file: {last_file_name}\n"
            f"Content preview:\n{preview}"
        )
    

    def _build_files_context(self) -> str:
        available_files = tools.list_input_files()

        if not available_files:
            return "No files available."

        return "Available files:\n" + "\n".join(f"- {file_name}" for file_name in available_files)


    def _build_dirs_context(self, approved_dirs: list[str]) -> str:
        if not approved_dirs:
            return "No directories have been granted access yet."

        active_directory = ""

        if self.filesystem_guard is not None:
            try:
                active_directory = self.filesystem_guard.get_active_directory()
            except AttributeError:
                active_directory = ""

        lines = ["Approved directories:"]

        for directory in approved_dirs:
            marker = " (ACTIVE)" if directory == active_directory else ""
            lines.append(f"- {directory}{marker}")

        lines.append("")
        lines.append("Important path rule:")
        lines.append("- Relative paths must be resolved inside the ACTIVE directory unless the user explicitly names another approved directory.")

        return "\n".join(lines)

    
    # ===== Parsing / Validation Helpers =====
    def _extract_json(self, text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in planner response.")

        return cleaned[start:end + 1]
    

    def _fallback_plan(self, error_message: str) -> dict:
        return {
            "plan_text": error_message,
            "needs_memory": False,
            "needs_executor": False,
            "needs_review": False,
            "executor_actions": [],
            "memory_action": "NONE",
            "memory_input": "NONE",
            "response_mode": "RAW",
            "target_source": "NONE",
            "transformation": "NONE",
        }


    def _parse_plan(self, raw_plan: str) -> dict:
        try:
            json_text = self._extract_json(raw_plan)
            plan = json.loads(json_text)
        except Exception as e:
            self._debug("JSON PARSE ERROR", e)
            self._debug("RAW INVALID PLAN", raw_plan)
            return self._fallback_plan(f"Planner returned invalid JSON: {e}")

        return self._validate_plan(plan)
    

    def _validate_plan(self, plan: dict) -> dict:
        valid_executor_actions = {
            "get_current_time",
            "list_input_files",
            "read_file",
            "read_multiple_files",
            "list_directory",
            "view_file",
            "find_file",
            "run_python_file",
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

        valid_memory_actions = {
            "NONE",
            "get_first_user_prompt",
            "get_last_user_prompt",
            "get_short_term_context",
            "get_last_active_file_name",
            "get_last_active_file_content",
            "get_previous_active_file_name",
            "get_previous_active_file_content",
            "search_long_term_memory",
            "list_recent_long_term_memories",
            "delete_long_term_memory",
            "save_accessible_path",
            "list_accessible_paths",
            "revoke_accessible_path",
        }

        valid_response_modes = {"RAW", "TRANSFORM", "ANSWER", "EXECUTE"}
        valid_target_sources = {"NONE", "MEMORY", "EXECUTOR", "BOTH"}
        valid_transformations = {"NONE", "SUMMARISE", "EXPLAIN", "EXTRACT", "EXECUTE_INSTRUCTIONS"}

        validated = {
            "plan_text": str(plan.get("plan_text", "")),
            "needs_memory": bool(plan.get("needs_memory", False)),
            "needs_executor": bool(plan.get("needs_executor", False)),
            "needs_review": bool(plan.get("needs_review", False)),
            "memory_action": str(plan.get("memory_action", "NONE")),
            "memory_input": str(plan.get("memory_input", "NONE")),
            "executor_actions": [],
            "response_mode": str(plan.get("response_mode", "RAW")).upper(),
            "target_source": str(plan.get("target_source", "NONE")).upper(),
            "transformation": str(plan.get("transformation", "NONE")).upper(),
        }

        raw_actions = plan.get("executor_actions", [])

        if not isinstance(raw_actions, list):
            raw_actions = []

        for item in raw_actions:
            if not isinstance(item, dict):
                continue

            action = str(item.get("action", "")).strip()
            action_input = str(item.get("input", "")).strip()

            if action in valid_executor_actions:
                validated["executor_actions"].append({
                    "action": action,
                    "input": action_input,
                })

        if validated["memory_action"] not in valid_memory_actions:
            validated["memory_action"] = "NONE"
            validated["memory_input"] = "NONE"

        if validated["response_mode"] not in valid_response_modes:
            validated["response_mode"] = "RAW"

        if validated["target_source"] not in valid_target_sources:
            validated["target_source"] = "NONE"

        if validated["transformation"] not in valid_transformations:
            validated["transformation"] = "NONE"

        return validated
    

    def _validate_next_step(self, step: dict) -> dict:
        valid_actions = {
            "NONE",
            "list_directory",
            "view_file",
            "find_file",
            "run_python_file",
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

        status = str(step.get("status", "FINISH")).upper()
        action = str(step.get("action", "NONE")).strip()
        action_input = str(step.get("input", "")).strip()

        if status not in {"CONTINUE", "FINISH"}:
            status = "FINISH"

        if action not in valid_actions:
            action = "NONE"

        if status == "FINISH":
            action = "NONE"
            action_input = ""

        return {
            "thought_summary": str(step.get("thought_summary", "")),
            "status": status,
            "action": action,
            "input": action_input,
            "final_response": str(step.get("final_response", "")),
        }
    

    # ===== Path / Normalisation Helpers ======
    def _deduplicate_create_file_actions(self, executor_actions: list[dict]) -> list[dict]:
        """
        Prevent plans like:
        create_file greeting.txt
        create_file greeting.txt::some content

        The second action tries to create the same file again and causes:
        Error: File already exists.

        If duplicates exist, prefer the version that already includes explicit content.
        Otherwise keep the first one.
        """
        selected_by_path = {}
        order = []

        for item in executor_actions:
            action = item.get("action", "")
            action_input = item.get("input", "")

            if action != "create_file":
                order.append(item)
                continue

            filepath = action_input.split("::", 1)[0].strip().strip("'\"")

            if not filepath:
                order.append(item)
                continue

            normalised_key = filepath.replace("\\", "/").lower()

            has_explicit_content = "::" in action_input

            if normalised_key not in selected_by_path:
                selected_by_path[normalised_key] = item
                order.append(item)
                continue

            existing_item = selected_by_path[normalised_key]
            existing_has_explicit_content = "::" in existing_item.get("input", "")

            # Prefer the duplicate that contains actual explicit content.
            if has_explicit_content and not existing_has_explicit_content:
                selected_by_path[normalised_key] = item

                for index, existing_order_item in enumerate(order):
                    if existing_order_item is existing_item:
                        order[index] = item
                        break

            # Otherwise ignore the duplicate.

        return order


    def _find_first_matching_path(self, root: Path, file_name: str) -> Path | None:
        try:
            for candidate in root.rglob(file_name):
                if any(part in SKIP_DIRECTORY_SUMMARY_DIRS for part in candidate.parts):
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

        parts = path.parts

        # If the first part of the path matches an approved directory name,
        # use that approved directory as the base.
        #
        # Example:
        # approved directory: /Users/jake/.../test3
        # input: test3/testing.txt
        # result: /Users/jake/.../test3/testing.txt
        if parts:
            first_part = parts[0].lower()

            for approved_dir in approved_dirs:
                approved_path = Path(approved_dir)
                approved_name = approved_path.name.lower()

                if first_part == approved_name:
                    remaining_path = Path(*parts[1:]) if len(parts) > 1 else Path()
                    candidate = approved_path / remaining_path

                    if must_exist:
                        if candidate.exists():
                            return str(candidate)

                        match = self._find_first_matching_path(approved_path, path.name)

                        if match is not None:
                            return str(match)

                    self._debug("ACTIVE DIRECTORY USED FOR RELATIVE PATH", approved_path)
                    self._debug("RELATIVE PATH CANDIDATE", candidate)
                    return str(candidate)

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

            match = self._find_first_matching_path(base_dir, path.name)

            if match is not None:
                return str(match)

        return str(candidate)
    

    def _input_file_exists(self, file_name: str) -> bool:
        try:
            return tools.find_file_in_input(file_name) is not None
        except Exception:
            return False
    
    
    def _looks_like_filesystem_path(self, value: str) -> bool:
        value = value.strip()

        if not value:
            return False

        possible_path = value.split("::", 1)[0].strip().strip("'\"")

        if not possible_path:
            return False

        return (
            "/" in possible_path
            or "\\" in possible_path
            or possible_path.startswith("~")
            or possible_path.startswith("/")
            or Path(possible_path).suffix != ""
        )
    

    def _looks_like_placeholder(self, value: str) -> bool:
        cleaned = value.strip().lower()

        if not cleaned:
            return False

        placeholder_markers = [
            "content of",
            "converted to",
            "same content",
            "same contents",
            "placeholder",
            "to be generated",
        ]

        return (
            cleaned.startswith("[")
            and cleaned.endswith("]")
            and any(marker in cleaned for marker in placeholder_markers)
        )
    

    def _normalize_plan(self, plan: dict, prompt: str) -> dict:
        lower_prompt = prompt.lower()
        executor_actions = plan.get("executor_actions", [])
        first_action = executor_actions[0]["action"] if executor_actions else "NONE"

        edit_words = {
            "edit",
            "modify",
            "change",
            "fix",
            "update",
            "separate",
            "seperate",
        }

        read_words = {
            "read",
            "look at",
            "open",
            "show",
            "view",
        }

        user_wants_edit = any(word in lower_prompt for word in edit_words)
        user_wants_read = any(word in lower_prompt for word in read_words)

        for item in executor_actions:
            action = item.get("action", "")
            action_input = item.get("input", "")

            if action in {"read_file", "view_file"} and self._input_file_exists(action_input):
                item["action"] = "read_file"
                item["input"] = action_input
                continue

            if self._looks_like_filesystem_path(action_input):
                cleaned_path = action_input.replace("\\", "/").strip().strip("'\"")

                approved_dirs = self._get_approved_directories()

                if approved_dirs:
                    active_root_name = Path(approved_dirs[-1]).name.lower()
                    parts = Path(cleaned_path).parts

                    if parts and parts[0].lower() == active_root_name:
                        cleaned_path = str(Path(*parts[1:]))

                if action == "read_file" and user_wants_edit:
                    item["action"] = "edit_file"
                    item["input"] = (
                        f"{cleaned_path}::"
                        "Edit the existing file in place. "
                    )

                elif action == "read_file" and user_wants_read:
                    item["action"] = "view_file"
                    item["input"] = cleaned_path

            action = item.get("action", "")
            action_input = item.get("input", "")

            if action == "write_file":
                parts = action_input.split("::", 1)
                filepath = parts[0].strip()
                content = parts[1] if len(parts) > 1 else ""

                resolved = self._resolve_relative_path(filepath)

                if not Path(resolved).exists():
                    item["action"] = "create_file"

                    if content and not self._looks_like_placeholder(content):
                        item["input"] = f"{filepath}::{content}"
                    else:
                        item["input"] = filepath

            if action == "read_file":
                candidate = self._resolve_relative_path(action_input, must_exist=True)

                if Path(candidate).exists():
                    item["action"] = "view_file"
                    item["input"] = action_input

        plan["executor_actions"] = executor_actions

        if plan["needs_executor"] and not executor_actions:
            plan["needs_executor"] = False

        if executor_actions:
            plan["needs_executor"] = True

        if plan["response_mode"] == "RAW":
            plan["transformation"] = "NONE"

        if plan["transformation"] != "NONE" and plan["response_mode"] == "ANSWER":
            plan["response_mode"] = "TRANSFORM"

        if plan["target_source"] == "NONE":
            if plan["memory_action"] != "NONE":
                plan["target_source"] = "MEMORY"
            elif executor_actions:
                plan["target_source"] = "EXECUTOR"

        if "other file" in lower_prompt:
            plan["needs_memory"] = True
            plan["memory_action"] = "get_previous_active_file_content"

            if plan["target_source"] == "NONE":
                plan["target_source"] = "MEMORY"

            if plan["response_mode"] == "RAW":
                plan["response_mode"] = "TRANSFORM"

            if plan["transformation"] == "NONE":
                plan["transformation"] = "EXPLAIN"

        if first_action == "read_multiple_files":
            plan["response_mode"] = "ANSWER"
            plan["needs_review"] = True
            plan["target_source"] = "EXECUTOR"
            plan["needs_executor"] = True

        if any(item["action"] in WRITE_ACTIONS for item in executor_actions):
            plan["response_mode"] = "RAW"
            plan["needs_review"] = False

        debug_markers = [
            "traceback",
            'file "',
            "line ",
            "typeerror",
            "valueerror",
            "syntaxerror",
            "nameerror",
            "attributeerror",
        ]

        if any(marker in lower_prompt for marker in debug_markers):
            plan["needs_review"] = False

        traceback_markers = ['file "', "line ", "traceback", "typeerror", "valueerror", "syntaxerror"]

        project_fix_words = [
            "fix",
            "repair",
            "complete",
            "continue",
            "make it run",
            "make it work",
            "incomplete",
            "missing",
        ]

        project_words = [
            "project",
            "codebase",
            "source code",
            ".py",
        ]

        only_reading = executor_actions and all(
            item.get("action") in INSPECTION_ACTIONS
            for item in executor_actions
        )

        if (
            any(word in lower_prompt for word in project_fix_words)
            and any(word in lower_prompt for word in project_words)
            and only_reading
        ):
            plan["plan_text"] = (
                "The planner produced only inspection actions for a project-fix request. "
                "This is incomplete; iterative mode should continue with edit/create/run actions."
            )
            plan["needs_review"] = False
            plan["response_mode"] = "RAW"
            plan["target_source"] = "EXECUTOR"
            plan["transformation"] = "NONE"

        if any(marker in lower_prompt for marker in traceback_markers):
            if plan["memory_action"] == "NONE" and not plan.get("executor_actions"):
                plan["needs_memory"] = True
                plan["memory_action"] = "get_last_active_file_content"
                plan["target_source"] = "MEMORY"
                plan["response_mode"] = "ANSWER"
                plan["needs_review"] = False

        for item in plan.get("executor_actions", []):
            action = item.get("action", "")
            action_input = item.get("input", "")

            if action in ("move_path", "copy_path") and "::" not in action_input and ":" in action_input:
                source, destination = action_input.split(":", 1)
                item["input"] = f"{source.strip()}::{destination.strip()}"

        for item in plan.get("executor_actions", []):
            action = item.get("action", "")
            action_input = item.get("input", "")

            if action == "run_python_file" and not action_input.strip():
                item["input"] = "main.py"

        last_active_content_actions = {
            "get_last_active_file_content",
            "get_previous_active_file_content",
        }

        if plan.get("memory_action") in last_active_content_actions:
            if any(word in lower_prompt for word in ["show", "display", "print", "content"]):
                plan["response_mode"] = "RAW"
                plan["target_source"] = "MEMORY"
                plan["transformation"] = "NONE"
                plan["needs_review"] = False

        for item in plan.get("executor_actions", []):
            action = item.get("action", "")
            action_input = item.get("input", "")

            if action != "move_path" or "::" not in action_input:
                continue

            source_text, destination_text = action_input.split("::", 1)

            source_clean = source_text.strip().strip("'\"")
            destination_clean = destination_text.strip().strip("'\"")

            # If the source looks like a file, never convert to move_directory_contents.
            if Path(source_clean).suffix:
                continue

            try:
                resolved_source = Path(
                    self._resolve_relative_path(source_clean, must_exist=True)
                ).resolve()

                resolved_destination = Path(
                    self._resolve_relative_path(destination_clean)
                ).resolve()

                # Only convert when the source is actually a directory
                # and the destination is inside that same directory.
                if (
                    resolved_source.exists()
                    and resolved_source.is_dir()
                    and resolved_source != resolved_destination
                    and resolved_source in resolved_destination.parents
                ):
                    item["action"] = "move_directory_contents"
                    item["input"] = action_input

            except Exception:
                pass


        plan["executor_actions"] = self._deduplicate_create_file_actions(
            plan.get("executor_actions", [])
        )

        return plan
    

    def create_next_step_after_repetition(self, original_prompt: str, observations: list[dict], repeated_action: str, repeated_input: str) -> dict:
        approved_dirs = self._get_approved_directories()

        observation_text_parts = []

        for index, observation in enumerate(observations, start=1):
            observation_text_parts.append(
                f"Step {index}\n"
                f"Action: {observation.get('action', '')}\n"
                f"Input: {observation.get('input', '')}\n"
                f"Result:\n{observation.get('result', '')}"
            )

        observation_text = "\n\n".join(observation_text_parts)

        used_action_text = "\n".join(
            f"- {observation.get('action', '')}::{observation.get('input', '')}"
            for observation in observations
        )

        planner_user_prompt = (
            f"User goal:\n{original_prompt}\n\n"
            f"{self._build_dirs_context(approved_dirs)}\n\n"
            f"Current approved directory context:\n"
            f"{self._build_directory_context(approved_dirs)}\n\n"
            f"Actions already used:\n"
            f"{used_action_text if used_action_text else 'None'}\n\n"
            f"The previous proposed action was rejected because it repeated this exact action:\n"
            f"{repeated_action}::{repeated_input}\n\n"
            f"You must now choose a DIFFERENT action/input pair.\n"
            f"Do not inspect the same folder or file again.\n"
            f"If a folder was already listed and is empty, create the next missing file needed for the user's goal.\n"
            f"If a file was already created, do not view it immediately. Continue creating the next missing file, run the project, or finish.\n"
            f"If you cannot decide safely, FINISH with a clear explanation.\n\n"
            f"Observations so far:\n"
            f"{observation_text if observation_text else 'No observations yet.'}\n\n"
            f"Choose the next step."
        )

        response = self.planning_client.ask(
            prompt=planner_user_prompt,
            system_prompt=prompts.iterative_planner_prompt,
            temperature=0,
            think=self.reasoning_settings.planner_think if self.reasoning_settings else "low",
        )

        if not response.ok:
            return {
                "thought_summary": response.error,
                "status": "FINISH",
                "action": "NONE",
                "input": "",
                "final_response": f"Planner error after repetition: {response.error}",
            }

        try:
            json_text = self._extract_json(response.content)
            step = json.loads(json_text)
        except Exception as e:
            return {
                "thought_summary": f"Planner returned invalid JSON after repetition: {e}",
                "status": "FINISH",
                "action": "NONE",
                "input": "",
                "final_response": f"Planner returned invalid JSON after repetition: {e}",
            }

        return self._validate_next_step(step)


    # ===== Public Planner Methods =====
    def create_plan(self, prompt: str, retrieved_memory_context: str = "") -> dict:
        approved_dirs = self._get_approved_directories()

        planner_user_prompt = (
            f"Recent context:\n{self._get_context()}\n\n"
            f"Retrieved long-term memory:\n"
            f"{retrieved_memory_context if retrieved_memory_context else 'None'}\n\n"
            f"{self._build_files_context()}\n\n"
            f"{self._build_dirs_context(approved_dirs)}\n\n"
            f"{self._build_directory_context(approved_dirs)}\n\n"
            f"File state:\n{self._build_file_state_context()}\n\n"
            f"User request:\n{prompt}"
        )

        plan_response = self.planning_client.ask(
            prompt=planner_user_prompt,
            system_prompt=prompts.planner_system_prompt,
            temperature=0,
            think=self.reasoning_settings.planner_think if self.reasoning_settings else "low",
        )

        if not plan_response.ok:
            self._debug("PLANNER LLM ERROR", plan_response.error)
            return self._fallback_plan(plan_response.error)

        self._debug("RAW PLAN", plan_response.content)

        parsed_plan = self._parse_plan(plan_response.content)
        normalized_plan = self._normalize_plan(parsed_plan, prompt)
        self._debug("PARSED PLAN", normalized_plan)
        return normalized_plan
    
    
    def create_next_step(self, original_prompt: str, observations: list[dict],  max_observation_chars: int = 12000) -> dict:
        approved_dirs = self._get_approved_directories()

        observation_text_parts = []

        for index, observation in enumerate(observations, start=1):
            observation_text_parts.append(
                f"Step {index}\n"
                f"Action: {observation.get('action', '')}\n"
                f"Input: {observation.get('input', '')}\n"
                f"Result:\n{observation.get('result', '')}"
            )

        observation_text = "\n\n".join(observation_text_parts)

        used_action_text = "\n".join(
            f"- {observation.get('action', '')}::{observation.get('input', '')}"
            for observation in observations
        )

        if len(observation_text) > max_observation_chars:
            observation_text = observation_text[-max_observation_chars:]

        planner_user_prompt = (
            f"User goal:\n{original_prompt}\n\n"
            f"{self._build_dirs_context(approved_dirs)}\n\n"
            f"Current approved directory context:\n"
            f"{self._build_directory_context(approved_dirs)}\n\n"
            f"Actions already used:\n"
            f"{used_action_text if used_action_text else 'None'}\n\n"
            f"Important:\n"
            f"- Actions already used is a strict ban list.\n"
            f"- You MUST NOT repeat any exact action/input pair listed above.\n"
            f"- You MUST NOT view the same file again unless an edit_file or write_file action changed that exact file after the previous view.\n"
            f"- Use file contents already shown in Observations so far instead of viewing the same file again.\n"
            f"- If a relevant file was already viewed, your next action must be edit_file, create_file, run_python_file, or FINISH.\n"
            f"- If you are unsure what to edit, use FINISH with a clear diagnosis instead of repeating inspection.\n\n"
            f"Observations so far:\n"
            f"{observation_text if observation_text else 'No observations yet.'}\n\n"
            f"Choose the next step."
        )

        response = self.planning_client.ask(
            prompt=planner_user_prompt,
            system_prompt=prompts.iterative_planner_prompt,
            temperature=0,
            think=self.reasoning_settings.planner_think if self.reasoning_settings else "low",
        )

        if not response.ok:
            return {
                "thought_summary": response.error,
                "status": "FINISH",
                "action": "NONE",
                "input": "",
                "final_response": f"Planner error: {response.error}",
            }

        try:
            json_text = self._extract_json(response.content)
            step = json.loads(json_text)
        except Exception as e:
            self._debug("RAW INVALID ITERATIVE PLAN", response.content)

            if not observations:
                return {
                    "thought_summary": "Fallback: inspect the active approved directory first.",
                    "status": "CONTINUE",
                    "action": "list_directory",
                    "input": "",
                    "final_response": "",
                }

            return {
                "thought_summary": f"Planner returned invalid JSON: {e}",
                "status": "FINISH",
                "action": "NONE",
                "input": "",
                "final_response": (
                    f"Planner returned invalid JSON after some observations: {e}\n\n"
                    f"Raw planner output:\n{response.content}"
                ),
            }

        return self._validate_next_step(step)
