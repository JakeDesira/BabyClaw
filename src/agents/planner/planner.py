from pathlib import Path
import re

from ollama_client import OllamaClient
import prompts
from tools.file_tools import list_input_files


class PlannerAgent:
    def __init__(self, memory=None, planning_model: str | None = None, filesystem_guard=None, debug: bool = True):
        self.memory = memory
        self.debug = debug
        self.filesystem_guard = filesystem_guard
        self.planning_client = OllamaClient(model=planning_model, supports_think=True)

    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[PLANNER DEBUG] {label}: {value}")

    def _get_context(self) -> str:
        if self.memory is None:
            return ""

        try:
            return self.memory.get_short_term_context()
        except AttributeError:
            return ""
        
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

                if entry.is_dir():
                    walk(entry, depth + 1)

        walk(root, 1)

        return "\n".join(lines) if lines else "(empty)"
    
    def _get_approved_directories(self) -> list[str]:
        if self.filesystem_guard is None:
            return []
        
        return self.filesystem_guard.list_approved()
    
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
        available_files = list_input_files()

        if not available_files:
            return "No files available."

        return "Available files:\n" + "\n".join(f"- {file_name}" for file_name in available_files)


    def _build_dirs_context(self, approved_dirs: list[str]) -> str:
        if not approved_dirs:
            return "No directories have been granted access yet."

        return (
            "Approved directories (use these paths when creating or editing files):\n"
            + "\n".join(f"- {directory}" for directory in approved_dirs)
        )
    
    
    def create_plan(self, prompt: str) -> dict:
        approved_dirs = self._get_approved_directories()

        planner_user_prompt = (
            f"Recent context:\n{self._get_context()}\n\n"
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
            think="low",
        )

        if not plan_response.ok:
            self._debug("PLANNER LLM ERROR", plan_response.error)
            return self._fallback_plan(plan_response.error)

        self._debug("RAW PLAN", plan_response.content)

        parsed_plan = self._parse_plan(plan_response.content)
        normalized_plan = self._normalize_plan(parsed_plan, prompt)
        self._debug("PARSED PLAN", normalized_plan)
        return normalized_plan
    
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
        cleaned = re.sub(r"<think>.*?</think>", "", raw_plan, flags=re.DOTALL).strip()

        result = {
            "plan_text": "",
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

        actions_mode = False

        for line in cleaned.splitlines():
            stripped = line.strip()
            upper_line = stripped.upper()

            if not stripped:
                continue

            if upper_line.startswith("MEMORY:"):
                actions_mode = False
                result["needs_memory"] = "YES" in upper_line

            elif upper_line.startswith("EXECUTOR:"):
                actions_mode = False
                result["needs_executor"] = "YES" in upper_line

            elif upper_line.startswith("REVIEW:"):
                actions_mode = False
                result["needs_review"] = "YES" in upper_line

            elif upper_line.startswith("PLAN:"):
                actions_mode = False
                result["plan_text"] = line.split(":", 1)[1].strip()

            elif upper_line.startswith("MEMORY_ACTION:"):
                actions_mode = False
                result["memory_action"] = line.split(":", 1)[1].strip()

            elif upper_line.startswith("MEMORY_INPUT:"):
                actions_mode = False
                result["memory_input"] = line.split(":", 1)[1].strip()

            elif upper_line.startswith("ACTIONS:"):
                actions_mode = True
                value = line.split(":", 1)[1].strip() if ":" in line else ""

                if value.upper() == "NONE":
                    result["executor_actions"] = []
                    actions_mode = False

                continue

            elif upper_line.startswith("RESPONSE_MODE:"):
                actions_mode = False
                result["response_mode"] = line.split(":", 1)[1].strip().upper()

            elif upper_line.startswith("TARGET_SOURCE:"):
                actions_mode = False
                result["target_source"] = line.split(":", 1)[1].strip().upper()

            elif upper_line.startswith("TRANSFORMATION:"):
                actions_mode = False
                result["transformation"] = line.split(":", 1)[1].strip().upper()

            elif actions_mode:
                action = self._parse_action_line(stripped)

                if action is not None:
                    result["executor_actions"].append(action)

        return self._validate_plan(result)
    
    def _parse_action_line(self, line: str) -> dict | None:
        action_line = re.sub(r"^\d+\.\s*", "", line)
        action_line = re.sub(r"^-\s*", "", action_line).strip()

        if not action_line or action_line.upper() == "NONE":
            return None

        if "::" in action_line:
            action_name, action_input = action_line.split("::", 1)
        else:
            action_name, action_input = action_line, ""

        action_name = action_name.strip()
        action_input = action_input.strip()

        malformed_markers = [
            "\n- ",
            " - create_file::",
            " - move_path::",
            " - copy_path::",
            " - edit_file::",
            " - append_file::",
            " - delete_file::",
            " - create_directory::",
            " - rename_path::",
        ]

        for marker in malformed_markers:
            if marker in action_input:
                action_input = action_input.split(marker, 1)[0].strip()

        return {
            "action": action_name,
            "input": action_input,
        }
    

    def _validate_plan(self, plan: dict) -> dict:
        valid_executor_actions = {
            "get_current_time",
            "list_input_files",
            "read_file",
            "read_multiple_files",
            "list_directory",
            "view_file",
            "create_file",
            "append_file",
            "delete_file",
            "edit_file",
            "create_directory",
            "move_path",
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
        }

        valid_response_modes = {"RAW", "TRANSFORM", "ANSWER", "EXECUTE"}
        valid_target_sources = {"NONE", "MEMORY", "EXECUTOR", "BOTH"}
        valid_transformations = {"NONE", "SUMMARISE", "EXPLAIN", "EXTRACT", "EXECUTE_INSTRUCTIONS"}

        plan["executor_actions"] = [
            item for item in plan["executor_actions"]
            if item["action"] in valid_executor_actions
        ]

        if plan["memory_action"] not in valid_memory_actions:
            plan["memory_action"] = "NONE"

        if plan["response_mode"] not in valid_response_modes:
            plan["response_mode"] = "RAW"

        if plan["target_source"] not in valid_target_sources:
            plan["target_source"] = "NONE"

        if plan["transformation"] not in valid_transformations:
            plan["transformation"] = "NONE"

        return plan
    

    def _normalize_plan(self, plan: dict, prompt: str) -> dict:
        lower_prompt = prompt.lower()
        executor_actions = plan.get("executor_actions", [])
        first_action = executor_actions[0]["action"] if executor_actions else "NONE"

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

        write_actions = {
            "create_directory",
            "create_file",
            "edit_file",
            "delete_file",
            "append_file",
            "move_path",
            "copy_path",
            "rename_path",
        }

        if any(item["action"] in write_actions for item in executor_actions):
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

            if action == "move_path" and "::" not in action_input and ":" in action_input:
                source, destination = action_input.split(":", 1)
                item["input"] = f"{source.strip()}::{destination.strip()}"

        return plan