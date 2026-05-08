import json
import re
from pathlib import Path

from action_constants import (
    CODE_MUTATING_ACTIONS,
    INSPECTION_ACTIONS,
    WRITE_ACTIONS,
)
from config import MAX_ITERATIVE_STEPS
from ollama_client import OllamaClient
import prompts


class CoordinatorAgent:
    """Route user requests through memory, planning, execution, and review."""
    def __init__(self, planner=None, plan_executor=None, response_generator=None, reviewer=None, memory=None, memory_router=None, memory_writer=None, model: str | None = None, reasoning_settings=None, debug: bool = True, trace_callback=None):
        """
        Entry point of the Baby Claw architecture.

        The Coordinator decides whether a request is simple enough to answer
        directly or whether it should be delegated into the planning pipeline.
        Memory retrieval is checked separately because simple requests may still
        require remembered context.
        """
        self.client = OllamaClient(model=model)
        self.planner = planner
        self.plan_executor = plan_executor
        self.response_generator = response_generator
        self.reviewer = reviewer
        self.memory = memory
        self.memory_router = memory_router
        self.memory_writer = memory_writer
        self.reasoning_settings = reasoning_settings
        self.debug = debug
        self.last_trace = {}
        self.trace_callback = trace_callback


    def _debug(self, label: str, value) -> None:
        """Print a debug message when debug logging is enabled."""
        if self.debug:
            print(f"[COORDINATOR DEBUG] {label}: {value}")


    def set_trace_callback(self, trace_callback) -> None:
        """Set a callback that receives trace snapshots as work progresses."""
        self.trace_callback = trace_callback


    def _publish_trace_update(self) -> None:
        """Publish the current trace to an optional live-debug callback."""
        if self.trace_callback is None:
            return

        if not self.last_trace:
            return

        try:
            self.trace_callback(self.last_trace)
        except Exception as e:
            self._debug("TRACE CALLBACK ERROR", e)


    # ===== Memory Helpers =====
    def _get_short_term_context(self) -> str:
        """
        Retrieve short-term memory context if a Memory Agent is available.
        """
        if self.memory is None:
            return ""

        try:
            return self.memory.get_short_term_context()
        except AttributeError:
            return ""
        

    def _might_save_memory(self, prompt: str) -> bool:
        """Return whether the prompt may request a durable memory save.

        Delegates to MemoryWriter so the marker list lives in one place and
        cannot drift out of sync with the gate inside ``MemoryWriter.extract``.
        """
        if self.memory_writer is None:
            return False

        return self.memory_writer.looks_like_save_request(prompt)

        
    def _save_extracted_memories(self, prompt: str) -> str:
        """
        Use MemoryWriter to extract durable facts from the current prompt
        and save them through MemoryAgent.
        """
        if self.memory is None or self.memory_writer is None:
            return ""

        short_term_context = self._get_short_term_context()

        try:
            extraction = self.memory_writer.extract(
                user_prompt=prompt,
                short_term_context=short_term_context,
            )
        except Exception as e:
            self._debug("MEMORY WRITER ERROR", e)
            return ""

        self._debug("MEMORY WRITER DECISION", extraction)

        if not extraction.get("should_save", False):
            return ""

        saved_results = []

        for memory_item in extraction.get("memories", []):
            content = memory_item.get("content", "").strip()
            memory_type = memory_item.get("memory_type", "general")
            importance = memory_item.get("importance", 1)

            if not content:
                continue

            try:
                result = self.memory.save_long_term_memory_if_new(
                    content=content,
                    memory_type=memory_type,
                    source="conversation",
                    importance=importance,
                )
                saved_results.append(result)
            except Exception as e:
                saved_results.append(f"Error saving memory '{content}': {e}")

        if not saved_results:
            return ""

        return "\n".join(saved_results)
        

    def _get_relevant_long_term_memory(self, prompt: str) -> str:
        """
        Retrieve long-term memory when the memory router thinks it may help.

        This is intentionally separate from the planner.
        A request can be simple but still need memory, for example:
        - What is my name?
        """
        if self.memory is None or self.memory_router is None:
            return ""

        short_term_context = self._get_short_term_context()

        try:
            decision = self.memory_router.check(
                user_prompt=prompt,
                short_term_context=short_term_context,
            )
        except Exception as e:
            self._debug("MEMORY ROUTER ERROR", e)
            return ""

        self._debug("MEMORY ROUTER DECISION", decision)

        if not decision.get("needs_memory", False):
            return ""

        search_query = decision.get("search_query", "").strip()

        if not search_query:
            search_query = prompt

        
        query_memory = self.memory.search_long_term_memory(search_query)

        profile_memory = ""

        try:
            profile_memory = self.memory.get_profile_memory()
        except AttributeError:
            profile_memory = ""

        parts = []

        if query_memory.strip() and query_memory.strip() != "No matching long-term memories found.":
            parts.append(query_memory)

        if profile_memory.strip() and profile_memory.strip() != "No matching long-term memories found.":
            parts.append(profile_memory)

        combined = "\n\n".join(parts)

        if not combined.strip():
            return ""

        return combined
    

    def _save_assistant_response(self, response: str) -> None:
        """
        Avoids repeating the same memory-save block multiple times.
        """
        if self.memory is None:
            return
        try:
            self.memory.save_short_term(role="assistant", content=response)
        except AttributeError:
            pass

    
    # ===== Routing Helpers =====
    def _get_approved_directories(self) -> list[str]:
        """Return approved workspace directories from the filesystem guard."""
        if self.plan_executor is not None:
            filesystem_guard = getattr(self.plan_executor, "filesystem_guard", None)

            if filesystem_guard is not None:
                try:
                    return filesystem_guard.list_approved()
                except AttributeError:
                    pass

        if self.planner is not None:
            filesystem_guard = getattr(self.planner, "filesystem_guard", None)

            if filesystem_guard is not None:
                try:
                    return filesystem_guard.list_approved()
                except AttributeError:
                    pass

        return []


    def _normalise_directory_match_text(self, text: str) -> str:
        """Normalise text for fuzzy directory-name matching."""
        lowered = text.lower().replace("\\", "/")
        return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


    def _detect_task_working_directory(self, prompt: str) -> str:
        """Detect an approved directory mentioned in the prompt."""
        approved_dirs = self._get_approved_directories()

        if not approved_dirs:
            return ""

        prompt_path_text = prompt.lower().replace("\\", "/")
        prompt_match_text = self._normalise_directory_match_text(prompt)

        matches = []

        for directory in approved_dirs:
            directory_path = Path(directory)
            directory_name = directory_path.name

            normalised_name = self._normalise_directory_match_text(directory_name)
            normalised_full_path = str(directory_path).lower().replace("\\", "/")

            full_path_mentioned = normalised_full_path in prompt_path_text
            folder_name_mentioned = normalised_name and normalised_name in prompt_match_text

            if full_path_mentioned or folder_name_mentioned:
                matches.append(str(directory_path))

        if not matches:
            return ""

        # Prefer the most specific match if multiple approved folders are mentioned.
        matches.sort(key=len, reverse=True)
        return matches[0]


    def _set_task_working_directory_from_prompt(self, prompt: str) -> str:
        """Set the task working directory when the prompt names one."""
        task_directory = self._detect_task_working_directory(prompt)

        if not task_directory:
            return ""

        if self.plan_executor is not None:
            try:
                self.plan_executor.set_task_working_directory(task_directory)
                self._debug("TASK WORKING DIRECTORY", task_directory)
            except AttributeError:
                self._debug(
                    "TASK WORKING DIRECTORY ERROR",
                    "PlanExecutor does not support set_task_working_directory yet.",
                )

        return task_directory


    def _normalise_action_key(self, action: str, action_input: str) -> str:
        """
        Create a stable key for detecting repeated iterative actions.
        """
        return f"{action.strip()}::{action_input.strip()}"


    def _is_write_action(self, action: str) -> bool:
        """
        Return True if an action changes the filesystem.
        """
        return action in WRITE_ACTIONS


    def _is_inspection_action(self, action: str) -> bool:
        """
        Return True if an action only inspects project state.
        """
        return action in INSPECTION_ACTIONS
    

    def _looks_like_debug_fragment(self, prompt: str) -> bool:
        """Return whether the prompt looks like a pasted traceback or error fragment."""
        lower_prompt = prompt.lower().strip()

        debug_markers = [
            "traceback",
            'file "',
            "line ",
            "typeerror",
            "valueerror",
            "syntaxerror",
            "nameerror",
            "attributeerror",
            "keyboardinterrupt",
            "indexerror",
            "keyerror",
            "modulenotfounderror",
            "importerror",
            "draw_borders(",
            "main(stdscr)",
            "for x in range(",
            "for y in range(",
        ]

        if any(marker in lower_prompt for marker in debug_markers):
            return True

        if lower_prompt.startswith("file \"") or lower_prompt.startswith("traceback"):
            return True

        return False


    def _extract_babyclaw_trace_and_remainder(self, prompt: str) -> tuple[dict, str]:
        """Return a pasted BabyClaw trace and any non-trace user instruction."""
        cleaned = prompt.strip()

        if not cleaned:
            return {}, ""

        candidates = [(cleaned, 0, len(prompt))]

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end != -1 and end > start:
            leading_offset = len(prompt) - len(prompt.lstrip())
            candidates.append((
                cleaned[start:end + 1],
                leading_offset + start,
                leading_offset + end + 1,
            ))

        for candidate, span_start, span_end in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue

            if not isinstance(parsed, dict):
                continue

            if self._is_babyclaw_trace_data(parsed):
                remainder = (
                    prompt[:span_start].strip()
                    + "\n"
                    + prompt[span_end:].strip()
                ).strip()
                return parsed, remainder

        return {}, ""


    def _is_babyclaw_trace_data(self, value: dict) -> bool:
        """Return whether parsed JSON resembles a BabyClaw internal trace."""
        if not isinstance(value, dict):
            return False

        trace_keys = {
            "plan",
            "planner_steps",
            "steps",
            "execution_data",
            "snapshot_result",
            "stop_reason",
            "final_step",
        }

        matched_keys = sum(1 for key in trace_keys if key in value)

        if matched_keys >= 2:
            return True

        plan = value.get("plan", {})

        return (
            isinstance(plan, dict)
            and (
                plan.get("mode") == "ITERATIVE"
                or isinstance(plan.get("planner_steps"), list)
                or isinstance(plan.get("executor_actions"), list)
            )
        )


    def _summarise_pasted_trace(self, trace: dict) -> str:
        """Return a safe diagnostic response for a pasted internal trace."""
        parts = [
            "I read this as a BabyClaw internal trace, so I will not execute the actions inside it.",
        ]

        stop_reason = trace.get("stop_reason", "")

        if stop_reason:
            parts.append(f"Stop reason: {stop_reason}")

        execution_data = trace.get("execution_data", {})
        steps = trace.get("steps", [])

        if not steps and isinstance(execution_data, dict):
            steps = execution_data.get("steps", [])

        planner_steps = trace.get("planner_steps", [])

        if not planner_steps:
            plan = trace.get("plan", {})

            if isinstance(plan, dict):
                planner_steps = plan.get("planner_steps", [])

        if steps:
            first_step = steps[0]
            active_directory = first_step.get("resolved_input", "")

            if active_directory:
                parts.append(f"Active directory inspected: {active_directory}")

        created_directories = [
            step.get("resolved_input", "")
            for step in steps
            if step.get("ok") and step.get("action") == "create_directory"
        ]

        if created_directories:
            parts.append(
                "Directories created:\n- "
                + "\n- ".join(created_directories[:8])
            )

        failed_steps = [
            step
            for step in steps
            if not step.get("ok", False)
            and step.get("action") != "completion_check"
        ]

        if failed_steps:
            latest_failure = failed_steps[-1]
            failure_text = latest_failure.get("result", "").strip()

            if failure_text:
                parts.append(f"Latest failing action: {failure_text}")

        completion_failures = [
            step.get("result", "")
            for step in steps
            if step.get("action") == "completion_check"
        ]

        if completion_failures:
            parts.append(completion_failures[-1])

        if planner_steps:
            last_planner_step = planner_steps[-1]
            action = last_planner_step.get("action", "")
            action_input = last_planner_step.get("input", "")

            if action:
                parts.append(f"Last planner action: {action} {action_input}".strip())

        if stop_reason == "Maximum iterative steps reached.":
            parts.append(
                "This usually means the agent spent too many steps debugging or filling structure "
                "and hit the step limit before it could finish the remaining scaffold items."
            )

        parts.append(
            "The trace should be handled as diagnostic input. If you want BabyClaw to continue that project, "
            "ask it to continue the existing folder by path instead of pasting the trace as the task."
        )

        return "\n\n".join(parts)


    def _looks_like_file_operation(self, prompt: str) -> bool:
        """Return whether the prompt asks for a filesystem action on a file/folder/path."""
        lower_prompt = prompt.lower()

        filesystem_action_words = [
            "create",
            "move",
            "rename",
            "delete",
            "edit",
            "append",
            "write",
            "organise",
            "organize",
            "copy",
        ]

        filesystem_object_words = [
            "file",
            "folder",
            "directory",
            "path",
        ]

        return (
            any(action in lower_prompt for action in filesystem_action_words)
            and any(obj in lower_prompt for obj in filesystem_object_words)
        )
    

    def _looks_like_direct_writing_task(self, prompt: str) -> bool:
        """Return whether the prompt asks for an in-chat draft (no file targets)."""
        lower_prompt = prompt.lower()

        writing_words = [
            "write",
            "draft",
            "compose",
            "rewrite",
            "re-write",
            "generate",
            "output",
            "show",
            "give",
            "provide",
        ]

        writing_objects = [
            "email",
            "message",
            "letter",
            "reply",
            "paragraph",
            "post",
            "code",
            "snippet",
            "syntax",
            "example",
            "function",
        ]

        tool_or_file_words = [
            "file",
            "folder",
            "directory",
            "codebase",
            "project",
            "save",
            "send",
            "append",
            "overwrite",
            "edit the file",
            "write it to",
            "put it in",
            "pdf",
            "attached",
            "attachment",
            "uploaded",
            "input file",
            "document",
            "from memory",
            "use my information",
            "my information",
            "my details",
        ]

        return (
            any(word in lower_prompt for word in writing_words)
            and any(obj in lower_prompt for obj in writing_objects)
            and not any(word in lower_prompt for word in tool_or_file_words)
        )
    

    def _looks_like_directory_listing(self, prompt: str) -> bool:
        """Return whether the prompt asks to list an approved or current directory."""
        lower_prompt = prompt.lower()

        return (
            "list" in lower_prompt
            and (
                "approved directory" in lower_prompt
                or "approved folder" in lower_prompt
                or "current directory" in lower_prompt
                or "current folder" in lower_prompt
            )
        )


    def _is_short_follow_up(self, prompt: str) -> bool:
        """Return whether the prompt is a one-word affirmative follow-up."""
        lower_prompt = prompt.lower().strip()

        short_follow_ups = {
            "yes",
            "yeah",
            "yep",
            "ok",
            "okay",
            "good",
            "do it",
            "fix it",
            "go on",
            "continue",
        }

        return lower_prompt in short_follow_ups
    

    def _looks_like_project_fix_task(self, prompt: str) -> bool:
        """Return whether the prompt asks to fix/repair/continue a Python project."""
        lower_prompt = prompt.lower()

        project_words = [
            "project",
            "codebase",
            "source code",
            "program",
            "app",
            ".py",
            "main.py",
        ]

        fix_words = [
            "fix",
            "repair",
            "debug",
            "complete",
            "continue",
            "make it run",
            "make it work",
            "not working",
            "broken",
            "incomplete",
            "missing",
            "error",
        ]

        return (
            any(word in lower_prompt for word in project_words)
            and any(word in lower_prompt for word in fix_words)
        )
    

    def _looks_like_project_build_task(self, prompt: str) -> bool:
        """Return whether the prompt asks to scaffold a new project/repo/app."""
        lower_prompt = prompt.lower()

        build_words = [
            "create",
            "build",
            "make",
            "generate",
            "scaffold",
            "set up",
            "setup",
        ]

        project_words = [
            "project",
            "repo",
            "repository",
            "pipeline",
            "app",
            "program",
            "game",
            "codebase",
        ]

        return (
            any(word in lower_prompt for word in build_words)
            and any(word in lower_prompt for word in project_words)
        )


    def _requires_scaffold_completion_check(self, prompt: str) -> bool:
        """Return whether a project build should pass structural completion checks."""
        if not self._looks_like_project_build_task(prompt):
            return False

        lower_prompt = prompt.lower()
        strict_markers = [
            "complete",
            "whole",
            "full",
            "entire",
            "pipeline",
            "from scratch",
        ]

        return any(marker in lower_prompt for marker in strict_markers)


    def _get_resolved_step_path(self, step_result: dict) -> Path | None:
        """Extract the filesystem path targeted by a completed step."""
        raw_input = str(step_result.get("resolved_input", "")).split("::", 1)[0].strip()

        if not raw_input:
            return None

        try:
            return Path(raw_input).expanduser().resolve()
        except Exception:
            return Path(raw_input).expanduser()


    def _path_exists_or_touched(self, path: Path, touched_paths: set[Path]) -> bool:
        """Return whether a path exists now or was touched in the current trace."""
        try:
            resolved_path = path.expanduser().resolve()
        except Exception:
            resolved_path = path.expanduser()

        if resolved_path in touched_paths:
            return True

        try:
            return resolved_path.exists()
        except Exception:
            return False


    def _maybe_set_created_project_directory(
        self,
        prompt: str,
        action: str,
        step_result: dict,
    ) -> None:
        """Use the first created project folder as the task working directory."""
        if (
            self.plan_executor is None
            or action != "create_directory"
            or not step_result.get("ok", False)
            or not self._requires_scaffold_completion_check(prompt)
        ):
            return

        filesystem_guard = getattr(self.plan_executor, "filesystem_guard", None)
        active_directory = ""

        if filesystem_guard is not None:
            try:
                active_directory = filesystem_guard.get_active_directory()
            except AttributeError:
                active_directory = ""

        existing_task_directory = getattr(self.plan_executor, "task_working_directory", "")

        if existing_task_directory and active_directory:
            try:
                if Path(existing_task_directory).resolve() != Path(active_directory).resolve():
                    return
            except Exception:
                return

        candidate = self._get_resolved_step_path(step_result)

        if candidate is None:
            return

        base_directory = existing_task_directory or active_directory

        if not base_directory:
            return

        try:
            base_path = Path(base_directory).expanduser().resolve()
            candidate_path = candidate.expanduser().resolve()
        except Exception:
            return

        if candidate_path.parent != base_path:
            return

        utility_directory_names = {
            "src",
            "tests",
            "test",
            "docs",
            "documentation",
            "assets",
        }

        if candidate_path.name.lower() in utility_directory_names:
            return

        try:
            self.plan_executor.set_task_working_directory(str(candidate_path))
            self._debug("ITERATIVE PROJECT WORKING DIRECTORY", str(candidate_path))
        except AttributeError:
            pass


    def _get_scaffold_project_root(self, steps_trace: list[dict]) -> Path | None:
        """Return the likely project root for an iterative scaffold trace."""
        if self.plan_executor is not None:
            task_directory = getattr(self.plan_executor, "task_working_directory", "")

            if task_directory:
                try:
                    return Path(task_directory).expanduser().resolve()
                except Exception:
                    return Path(task_directory).expanduser()

        for step in steps_trace:
            if step.get("action") != "create_directory" or not step.get("ok", False):
                continue

            path = self._get_resolved_step_path(step)

            if path is not None:
                return path

        return None


    def _get_scaffold_completion_issues(
        self,
        prompt: str,
        steps_trace: list[dict],
    ) -> list[str]:
        """Return missing items that make a full project scaffold incomplete."""
        if not self._requires_scaffold_completion_check(prompt):
            return []

        root = self._get_scaffold_project_root(steps_trace)

        if root is None:
            return ["project root directory"]

        touched_paths: set[Path] = set()

        for step in steps_trace:
            if not step.get("ok", False):
                continue

            path = self._get_resolved_step_path(step)

            if path is None:
                continue

            touched_paths.add(path)

        issues = []

        if not self._path_exists_or_touched(root / "README.md", touched_paths):
            issues.append("README.md inside the project root")

        has_python_files = any(
            path.suffix.lower() == ".py"
            and path.is_relative_to(root)
            for path in touched_paths
        )

        if not has_python_files:
            try:
                has_python_files = any(root.rglob("*.py"))
            except Exception:
                has_python_files = False

        if not has_python_files:
            return issues

        required_paths = {
            "main.py inside the project root": root / "main.py",
            "src directory inside the project root": root / "src",
            "src/__init__.py for package initialization": root / "src" / "__init__.py",
            "tests directory inside the project root": root / "tests",
        }

        for description, path in required_paths.items():
            if not self._path_exists_or_touched(path, touched_paths):
                issues.append(description)

        tests_dir = root / "tests"
        has_test_file = any(
            path.parent == tests_dir
            and path.suffix.lower() == ".py"
            and path.name.startswith("test_")
            for path in touched_paths
        )

        if not has_test_file:
            try:
                has_test_file = any(tests_dir.glob("test_*.py"))
            except Exception:
                has_test_file = False

        if not has_test_file:
            issues.append("at least one focused test file in tests/")

        return issues


    def _should_use_iterative_mode(self, prompt: str) -> bool:
        """Return whether the request should use iterative execution."""
        if self._looks_like_project_fix_task(prompt):
            self._debug("ITERATIVE ROUTER RULE", "Project fix task detected.")
            return True

        if self._looks_like_project_build_task(prompt):
            self._debug("ITERATIVE ROUTER RULE", "Project build task detected.")
            return True

        short_term_context = self._get_short_term_context()

        router_user_prompt = (
            f"Recent conversation context:\n"
            f"{short_term_context if short_term_context else 'None'}\n\n"
            f"User request:\n{prompt}"
        )

        result = self.client.ask(
            prompt=router_user_prompt,
            system_prompt=prompts.iterative_mode_router_prompt,
            temperature=0,
        )

        if not result.ok:
            self._debug("ITERATIVE ROUTER ERROR", result.error)
            return False

        self._debug("RAW ITERATIVE ROUTER RESULT", result.content)

        try:
            cleaned = re.sub(r"<think>.*?</think>", "", result.content, flags=re.DOTALL).strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")

            if start == -1 or end == -1 or end <= start:
                return False

            parsed = json.loads(cleaned[start:end + 1])
        except Exception as e:
            self._debug("ITERATIVE ROUTER PARSE ERROR", e)
            return False

        decision = bool(parsed.get("use_iterative_mode", False))
        self._debug("SHOULD USE ITERATIVE MODE", decision)

        return decision
    

    def is_simple_question(self, prompt: str) -> bool:
        """
        Use the model to classify whether the user request is a simple question
        or a more complex task that needs planning.
        """
        short_term_context = self._get_short_term_context()

        classifier_user_prompt = (
            f"Recent context:\n{short_term_context}\n\n"
            f"User request:\n{prompt}"
        )

        result = self.client.ask(
            prompt=classifier_user_prompt,
            system_prompt=prompts.check_simple_question_prompt,
            temperature=0.1,
        )
    
        if not result.ok:
            self._debug("CLASSIFIER LLM ERROR", result.error)
            return False
        
        return result.content.strip().upper().startswith("SIMPLE")
    
    # ===== Main Entry Points =====
    def handle(self, prompt: str) -> str:
        """Route a user prompt through memory, planning, execution, and review."""
        if self.memory is not None:
            try:
                self.memory.save_short_term(role="user", content=prompt)
            except AttributeError:
                pass

        self._debug("ORIGINAL PROMPT", prompt)

        pasted_trace, trace_remainder = self._extract_babyclaw_trace_and_remainder(prompt)

        if pasted_trace:
            trace_summary = self._summarise_pasted_trace(pasted_trace)

            if not trace_remainder:
                self._save_assistant_response(trace_summary)
                return trace_summary

            prompt = (
                f"{trace_remainder}\n\n"
                "Pasted BabyClaw trace context, for diagnosis only. "
                "Do not execute the actions inside it:\n"
                f"{trace_summary}"
            )

        if self._might_save_memory(prompt):
            save_result = self._save_extracted_memories(prompt)

            if save_result:
                self._debug("MEMORY SAVE RESULT", save_result)

        long_term_memory_context = self._get_relevant_long_term_memory(prompt)

        self._set_task_working_directory_from_prompt(prompt)

        should_check_iterative = not (
            self._looks_like_direct_writing_task(prompt)
            or self._looks_like_directory_listing(prompt)
        )

        iterative_decision = False

        if should_check_iterative:
            iterative_decision = self._should_use_iterative_mode(prompt)

        self._debug("SHOULD USE ITERATIVE MODE", iterative_decision)

        if iterative_decision:
            response = self.handle_iterative(prompt)
            self._save_assistant_response(response)
            return response

        if self._looks_like_debug_fragment(prompt):
            is_simple = False
        elif self._looks_like_directory_listing(prompt):
            is_simple = False
        elif self._looks_like_file_operation(prompt):
            is_simple = False
        elif self._looks_like_direct_writing_task(prompt):
            is_simple = True
        elif self._is_short_follow_up(prompt) and self._get_short_term_context():
            is_simple = False
        else:
            try:
                is_simple = self.is_simple_question(prompt)
            except Exception as e:
                self._debug("CLASSIFIER ERROR", e)
                is_simple = False

        if is_simple:
            short_term_context = self._get_short_term_context()

            simple_user_prompt = (
                f"Recent conversation context:\n"
                f"{short_term_context if short_term_context else 'None'}\n\n"
                f"Retrieved long-term memory:\n"
                f"{long_term_memory_context if long_term_memory_context else 'None'}\n\n"
                f"User request:\n{prompt}"
            )

            response_result = self.client.ask(
                prompt=simple_user_prompt,
                system_prompt=prompts.simple_response_prompt,
                temperature=0.2,
            )

            if response_result.ok:
                response = response_result.content
            else:
                self._debug("SIMPLE RESPONSE LLM ERROR", response_result.error)
                response = response_result.error

            self._save_assistant_response(response)
            return response

        if self.planner is None or self.plan_executor is None or self.response_generator is None:
            response = (
                "This task appears to require planning, but the planning pipeline "
                "has not been connected correctly yet."
            )

            self._save_assistant_response(response)
            return response

        current_prompt = prompt
        max_iterations = self.reasoning_settings.max_iterations if self.reasoning_settings else 3
        last_result = ""

        for iteration in range(max_iterations):
            self._debug("ITERATION", iteration + 1)
            self._debug("CURRENT PROMPT", current_prompt)

            plan = self.planner.create_plan(
                current_prompt,
                retrieved_memory_context=long_term_memory_context,
            )
            self.last_trace = {
                "plan": plan,
                "execution_data": {},
                "steps": [],
                "review": {},
            }
            self._publish_trace_update()
            self._debug("PLAN", plan)

            execution_data = self.plan_executor.execute_plan_once(prompt, plan)
            self.last_trace["execution_data"] = execution_data
            self.last_trace["steps"] = execution_data.get("steps", [])
            self._publish_trace_update()
            self._debug("EXECUTION DATA", execution_data)

            context = execution_data.get("context", "")
            execution_result = execution_data.get("execution_result", "")
            source_text = execution_data.get("source_text", "")
            error = execution_data.get("error", "")

            if error:
                last_result = error
                break

            response_mode = plan.get("response_mode", "RAW")
            transformation = plan.get("transformation", "NONE")

            if response_mode == "RAW":
                draft_result = (
                    source_text
                    or execution_result
                    or context
                    or "I could not retrieve the requested content."
                )

            elif response_mode == "TRANSFORM":
                if not source_text:
                    if plan.get("memory_action") == "get_previous_active_file_content":
                        draft_result = (
                            "There is no other file in memory yet. "
                            "Try reading a second file first."
                        )
                    else:
                        draft_result = (
                            "I could not retrieve the content needed for transformation."
                        )
                else:
                    draft_result = self.response_generator.transform_content(
                        prompt,
                        source_text,
                        transformation,
                    )

            elif response_mode == "ANSWER":
                combined_context_parts = []
                short_term_context = self._get_short_term_context()

                if short_term_context:
                    combined_context_parts.append(
                        "Recent conversation context:\n"
                        + short_term_context
                    )

                if long_term_memory_context:
                    combined_context_parts.append(
                        "Retrieved long-term memory:\n"
                        + long_term_memory_context
                    )

                if context:
                    combined_context_parts.append(
                        "Planner memory/tool context:\n"
                        + context
                    )

                combined_context = "\n\n".join(combined_context_parts)

                draft_result = self.response_generator.generate_final_response(
                    prompt=prompt,
                    context=combined_context,
                    execution_result=execution_result,
                )

            elif response_mode == "EXECUTE":
                if not source_text:
                    draft_result = (
                        "I could not retrieve the content needed to execute the instructions."
                    )
                else:
                    draft_result = self.response_generator.transform_content(
                        prompt,
                        source_text,
                        "EXECUTE_INSTRUCTIONS",
                    )

            else:
                draft_result = (
                    execution_result
                    or context
                    or "I understood the request, but I could not complete it reliably yet."
                )

            last_result = draft_result
            self._debug("DRAFT RESULT", draft_result)

            reviewer_allowed = self.reasoning_settings.allow_reviewer if self.reasoning_settings else True

            if self.reviewer is None or not plan.get("needs_review", False) or not reviewer_allowed:
                break

            review = self.reviewer.review(prompt, draft_result)
            self.last_trace["review"] = review
            self._publish_trace_update()
            self._debug("REVIEW RESULT", review)

            if review.get("approved", False):
                break

            current_prompt = (
                f"Original user request:\n{prompt}\n\n"
                f"Reviewer feedback on previous attempt:\n{review.get('feedback', '')}\n\n"
                "Please complete the remaining work."
            )

        response = last_result

        self._save_assistant_response(response)

        return response
    

    def _get_iterative_snapshot_metadata(self) -> dict:
        """Return snapshot metadata for iterative traces."""
        if self.plan_executor is None:
            return {
                "snapshot_result": "",
                "snapshot_path": "",
                "snapshot_target": "",
            }

        transaction_manager = getattr(self.plan_executor, "transaction_manager", None)

        if transaction_manager is None:
            return {
                "snapshot_result": "",
                "snapshot_path": "",
                "snapshot_target": "",
            }

        snapshot_path = ""
        snapshot_target = ""

        try:
            snapshot_path = transaction_manager.get_last_snapshot_path()
            snapshot_target = transaction_manager.get_last_target_path()
        except AttributeError:
            pass

        return {
            "snapshot_result": "",
            "snapshot_path": snapshot_path,
            "snapshot_target": snapshot_target,
        }
    
    def _action_input_targets_python_file(self, action_input: str) -> bool:
        """Return whether an action input targets a Python file."""
        target_path = action_input.split("::", 1)[0].strip().strip("'\"")

        if not target_path:
            return False

        target_path = target_path.replace("\\", "/")

        return target_path.lower().endswith((".py", ".pyw"))

    
    def handle_iterative(self, prompt: str, max_steps: int | None = None) -> str:
        """Run the iterative planning and execution loop.

        ``max_steps`` defaults to ``config.MAX_ITERATIVE_STEPS`` (override via
        the BABYCLAW_MAX_ITERATIVE_STEPS environment variable).
        """
        if max_steps is None:
            max_steps = MAX_ITERATIVE_STEPS

        self._set_task_working_directory_from_prompt(prompt)
        
        observations = []
        execution_results = []
        steps_trace = []
        planner_steps = []

        snapshot_result = ""

        used_action_keys = set()
        viewed_files_since_last_write = set()
        created_file_targets = set()
        made_successful_write = False
        changed_since_last_run = False
        completion_check_failures = 0

        def shorten_for_user(text: str, max_chars: int = 1200) -> str:
            """Trim long internal text for user-facing stop messages."""
            if not isinstance(text, str):
                return ""

            cleaned = text.strip()

            if len(cleaned) <= max_chars:
                return cleaned

            return cleaned[:max_chars] + "\n\n... [truncated]"

        def user_stop_message(reason: str, detail: str = "") -> str:
            """Build a concise user-facing stop message."""
            message = reason.strip()

            cleaned_detail = shorten_for_user(detail)

            if cleaned_detail:
                message += "\n\n" + cleaned_detail

            message += "\n\nCheck Debug / Internals for the full execution trace."

            return message

        def normalised_action_target(action_input: str) -> str:
            """Return a stable absolute target path for file actions."""
            target_text = action_input.split("::", 1)[0].strip().strip("'\"")

            if not target_text:
                return ""

            try:
                resolved = self.plan_executor._resolve_relative_path(target_text)
            except Exception:
                resolved = target_text

            try:
                return str(Path(resolved).expanduser().resolve())
            except Exception:
                return resolved

        def observation_result_for(action: str, step_result: dict) -> str:
            """Make tool observations explicit enough for the next planner step."""
            result_text = step_result.get("result", "")

            if (
                action == "create_file"
                and step_result.get("ok", False)
                and result_text.startswith("File created:")
            ):
                return (
                    f"{result_text}\n"
                    "The file was created and populated with generated content. "
                    "Do not call write_file for this same path unless fixing a verified problem."
                )

            return result_text

        def snapshot_metadata() -> dict:
            """Return current iterative snapshot metadata."""
            return self._get_iterative_snapshot_metadata()

        def set_trace(
            final_step=None,
            stop_reason: str = "",
            include_snapshot_top_level: bool = False,
        ) -> None:
            """Store the current iterative execution trace."""
            metadata = snapshot_metadata()

            trace = {
                "mode": "ITERATIVE",
                "plan": {
                    "plan_text": "Iterative mode: planner chooses one next action at a time.",
                    "mode": "ITERATIVE",
                    "planner_steps": planner_steps,
                },
                "planner_steps": planner_steps,
                "steps": steps_trace,
                "snapshot_result": snapshot_result,
                "execution_data": {
                    "snapshot_result": snapshot_result,
                    "snapshot_path": metadata["snapshot_path"],
                    "snapshot_target": metadata["snapshot_target"],
                    "steps": steps_trace,
                },
            }

            if final_step is not None:
                trace["final_step"] = final_step

            if stop_reason:
                trace["stop_reason"] = stop_reason

            if include_snapshot_top_level:
                trace["snapshot_path"] = metadata["snapshot_path"]
                trace["snapshot_target"] = metadata["snapshot_target"]

            self.last_trace = trace
            self._publish_trace_update()

        # Deterministic first step for project/directory inspection tasks.
        first_step_result = self.plan_executor.execute_single_action(
            prompt=prompt,
            action="list_directory",
            action_input="",
            previous_results=[],
        )

        first_action_key = self._normalise_action_key("list_directory", "")
        used_action_keys.add(first_action_key)

        observations.append(
            {
                "action": "list_directory",
                "input": "",
                "result": first_step_result.get("result", ""),
            }
        )

        steps_trace.append(first_step_result)
        execution_results.append(first_step_result.get("result", ""))
        set_trace()

        if not first_step_result.get("ok", False):
            set_trace(stop_reason="Initial directory inspection failed.")

            return user_stop_message(
                "I could not inspect the active directory.",
                first_step_result.get("result", ""),
            )

        for step_number in range(2, max_steps + 1):
            next_step = self.planner.create_next_step(
                original_prompt=prompt,
                observations=observations,
            )

            planner_steps.append(
                {
                    "step_number": step_number,
                    "type": "planner_next_step",
                    "thought_summary": next_step.get("thought_summary", ""),
                    "status": next_step.get("status", ""),
                    "action": next_step.get("action", ""),
                    "input": next_step.get("input", ""),
                    "final_response": next_step.get("final_response", ""),
                }
            )
            set_trace()

            self._debug("ITERATIVE NEXT STEP", next_step)

            status = next_step.get("status", "FINISH")
            action = next_step.get("action", "NONE")
            action_input = next_step.get("input", "")

            if status == "FINISH":
                final_response = next_step.get("final_response", "").strip()
                completion_issues = self._get_scaffold_completion_issues(
                    prompt,
                    steps_trace,
                )

                if completion_issues:
                    feedback = (
                        "Scaffold completion check failed. The project is not ready to finish yet. "
                        "Missing required items:\n- "
                        + "\n- ".join(completion_issues)
                    )

                    completion_check_failures += 1

                    if completion_check_failures <= 2:
                        observations.append(
                            {
                                "action": "completion_check",
                                "input": "",
                                "result": feedback,
                            }
                        )
                        execution_results.append(feedback)
                        steps_trace.append(
                            {
                                "ok": False,
                                "action": "completion_check",
                                "input": "",
                                "resolved_input": "",
                                "result": feedback,
                                "verification": {
                                    "ok": False,
                                    "feedback": feedback,
                                },
                            }
                        )
                        planner_steps[-1]["completion_check"] = feedback
                        self._debug("ITERATIVE COMPLETION CHECK", feedback)
                        set_trace()
                        continue

                    set_trace(
                        final_step=next_step,
                        stop_reason="Scaffold completion check failed.",
                        include_snapshot_top_level=True,
                    )

                    return user_stop_message(
                        "I stopped because the project scaffold is still incomplete.",
                        feedback,
                    )

                set_trace(final_step=next_step)

                if final_response:
                    return final_response

                return "Done."

            if action == "NONE":
                set_trace(
                    final_step=next_step,
                    stop_reason="Planner returned no action.",
                )

                return user_stop_message(
                    "I could not decide the next action."
                )

            action_target = normalised_action_target(action_input)

            if action == "write_file" and action_target in created_file_targets:
                skip_message = (
                    "Skipped redundant write_file for a file that was already created "
                    f"and populated in this run: {action_target}"
                )
                step_data = {
                    "ok": True,
                    "action": action,
                    "input": action_input,
                    "resolved_input": action_input,
                    "result": skip_message,
                    "verification": {
                        "ok": True,
                        "feedback": skip_message,
                    },
                }

                observations.append(
                    {
                        "action": action,
                        "input": action_input,
                        "result": (
                            f"{skip_message}\n"
                            "Use run_python_file, create the next missing file, or FINISH."
                        ),
                    }
                )
                steps_trace.append(step_data)
                execution_results.append(skip_message)
                used_action_keys.add(self._normalise_action_key(action, action_input))
                set_trace()
                continue

            action_key = self._normalise_action_key(action, action_input)

            # Allow rerunning the same Python entry point after code changed.
            # This is not a loop; it is the normal debug cycle:
            # run -> fail -> edit -> run again.
            if action == "run_python_file" and changed_since_last_run:
                pass
            elif action_key in used_action_keys:
                if action != "view_file":
                    retry_step = self.planner.create_next_step_after_repetition(
                        original_prompt=prompt,
                        observations=observations,
                        repeated_action=action,
                        repeated_input=action_input,
                    )

                    planner_steps.append(
                        {
                            "step_number": step_number,
                            "type": "planner_retry_after_repetition",
                            "thought_summary": retry_step.get("thought_summary", ""),
                            "status": retry_step.get("status", ""),
                            "action": retry_step.get("action", ""),
                            "input": retry_step.get("input", ""),
                            "final_response": retry_step.get("final_response", ""),
                            "repeated_action": action,
                            "repeated_input": action_input,
                        }
                    )
                    set_trace()

                    self._debug("ITERATIVE RETRY AFTER REPETITION", retry_step)

                    retry_status = retry_step.get("status", "FINISH")
                    retry_action = retry_step.get("action", "NONE")
                    retry_input = retry_step.get("input", "")

                    retry_key = self._normalise_action_key(retry_action, retry_input)

                    if (
                        retry_status != "CONTINUE"
                        or retry_action == "NONE"
                        or retry_key in used_action_keys
                    ):
                        if made_successful_write:
                            set_trace(
                                final_step=retry_step,
                                stop_reason=(
                                    "Planner repeated an action after a successful filesystem change, "
                                    "so the task was treated as complete."
                                ),
                            )

                            return "Done. The requested file changes were completed successfully."

                        bad_repeated_key = retry_key if retry_key in used_action_keys else action_key
                        bad_action = retry_action if retry_key in used_action_keys else action
                        bad_input = retry_input if retry_key in used_action_keys else action_input

                        set_trace(
                            final_step=retry_step,
                            stop_reason=f"Repeated iterative action detected: {bad_repeated_key}",
                        )

                        final_response = retry_step.get("final_response", "").strip()

                        if final_response:
                            return final_response

                        return user_stop_message(
                            "I stopped because the planner repeated an action and could not recover with a valid different next step.",
                            f"Repeated action: `{bad_action}` with input `{bad_input}`.",
                        )

                    action = retry_action
                    action_input = retry_input
                    action_key = retry_key

                else:
                    if not action_input.strip().endswith(".py"):
                        set_trace(
                            final_step=next_step,
                            stop_reason=f"Repeated non-Python file inspection detected: {action_key}",
                        )

                        return user_stop_message(
                            "I stopped because the planner repeated a file inspection, but the repeated file is not a Python file I should auto-edit.",
                            (
                                f"Repeated file: `{action_input}`.\n\n"
                                "The next step should be a clear `edit_file`, `create_file`, `run_python_file`, or `FINISH`."
                            ),
                        )

                    forced_action = "edit_file"
                    forced_input = (
                        f"{action_input}::"
                        "Use the file content already shown in the observations. "
                        "Apply the smallest targeted fix based on the observed API mismatches, "
                        "missing methods, broken imports, or runtime issue. "
                        "Preserve unrelated working code."
                    )

                    self._debug(
                        "REPEATED ACTION FALLBACK",
                        f"Forcing {forced_action} with input {forced_input}",
                    )

                    if (
                        self.plan_executor.transaction_manager is not None
                        and not snapshot_result
                    ):
                        snapshot_directory = self.plan_executor.get_snapshot_directory_for_action(
                            prompt=prompt,
                            action=forced_action,
                            action_input=forced_input,
                        )

                        if snapshot_directory:
                            snapshot_result = self.plan_executor.transaction_manager.snapshot_directory(
                                snapshot_directory
                            )
                        else:
                            snapshot_result = self.plan_executor.transaction_manager.snapshot_active_directory()

                        self._debug("ITERATIVE SNAPSHOT DIRECTORY", snapshot_directory)
                        self._debug("ITERATIVE SNAPSHOT RESULT", snapshot_result)

                        if snapshot_result.startswith("Error"):
                            set_trace(
                                final_step=next_step,
                                stop_reason="Snapshot creation failed.",
                            )

                            return user_stop_message(
                                "I could not create a safety snapshot before editing.",
                                snapshot_result,
                            )

                    step_result = self.plan_executor.execute_single_action(
                        prompt=prompt,
                        action=forced_action,
                        action_input=forced_input,
                        previous_results=execution_results,
                    )

                    observations.append(
                        {
                            "action": forced_action,
                            "input": forced_input,
                            "result": observation_result_for(forced_action, step_result),
                        }
                    )

                    steps_trace.append(step_result)
                    execution_results.append(step_result.get("result", ""))
                    self._maybe_set_created_project_directory(
                        prompt,
                        forced_action,
                        step_result,
                    )
                    set_trace()

                    if step_result.get("ok", False):
                        made_successful_write = True
                        changed_since_last_run = True
                        viewed_files_since_last_write.clear()

                        if forced_action == "create_file":
                            created_target = normalised_action_target(forced_input)

                            if created_target:
                                created_file_targets.add(created_target)

                        used_action_keys.add(
                            self._normalise_action_key(forced_action, forced_input)
                        )
                        continue

                    # Do not automatically rollback here.
                    # Automatic rollback can be dangerous on Windows/Google Drive because restoring
                    # a whole directory may partially delete the target if access is denied.

                    set_trace(
                        stop_reason="Repeated inspection fallback failed.",
                    )

                    return user_stop_message(
                        "I stopped because the repeated-inspection recovery step failed.",
                        step_result.get("result", ""),
                    )

            normalised_view_file = ""

            # Prevent viewing the same file repeatedly before any edit/write happens.
            if action == "view_file":
                normalised_view_file = action_input.strip()

                if normalised_view_file in viewed_files_since_last_write:
                    set_trace(
                        final_step=next_step,
                        stop_reason=(
                            "Repeated file view detected before any write action: "
                            f"{normalised_view_file}"
                        ),
                    )

                    return user_stop_message(
                        "I stopped because the agent tried to view the same file again without making progress.",
                        (
                            f"The repeated file was: `{normalised_view_file}`.\n\n"
                            "The next step should be editing the faulty file, creating a missing file, "
                            "or finishing with a clear diagnosis."
                        ),
                    )

            if normalised_view_file:
                viewed_files_since_last_write.add(normalised_view_file)

            used_action_keys.add(action_key)

            if (
                self.plan_executor.transaction_manager is not None
                and not snapshot_result
                and self._is_write_action(action)
            ):
                snapshot_directory = self.plan_executor.get_snapshot_directory_for_action(
                    prompt=prompt,
                    action=action,
                    action_input=action_input,
                )

                if snapshot_directory:
                    snapshot_result = self.plan_executor.transaction_manager.snapshot_directory(
                        snapshot_directory
                    )
                else:
                    snapshot_result = self.plan_executor.transaction_manager.snapshot_active_directory()

                self._debug("ITERATIVE SNAPSHOT DIRECTORY", snapshot_directory)
                self._debug("ITERATIVE SNAPSHOT RESULT", snapshot_result)

                if snapshot_result.startswith("Error"):
                    set_trace(
                        final_step=next_step,
                        stop_reason="Snapshot creation failed.",
                    )

                    return user_stop_message(
                        "I could not create a safety snapshot before changing files.",
                        snapshot_result,
                    )

                metadata = snapshot_metadata()
                self._debug("ITERATIVE SNAPSHOT PATH", metadata["snapshot_path"])
                self._debug("ITERATIVE SNAPSHOT TARGET", metadata["snapshot_target"])

            step_result = self.plan_executor.execute_single_action(
                prompt=prompt,
                action=action,
                action_input=action_input,
                previous_results=execution_results,
            )

            observations.append(
                {
                    "action": action,
                    "input": action_input,
                    "result": observation_result_for(action, step_result),
                }
            )

            steps_trace.append(step_result)
            execution_results.append(step_result.get("result", ""))
            self._maybe_set_created_project_directory(prompt, action, step_result)
            set_trace()

            if step_result.get("ok", False) and self._is_write_action(action):
                made_successful_write = True
                viewed_files_since_last_write.clear()

                if action == "create_file":
                    created_target = normalised_action_target(action_input)

                    if created_target:
                        created_file_targets.add(created_target)

                if (
                    action in CODE_MUTATING_ACTIONS
                    and self._action_input_targets_python_file(action_input)
                ):
                    changed_since_last_run = True

            if action == "run_python_file":
                changed_since_last_run = False

            if not step_result.get("ok", False):
                if action == "run_python_file":
                    continue

                # Do not automatically rollback here.
                # Rollback should be manual through the GUI safety button.
                set_trace(
                    stop_reason="Action failed.",
                    include_snapshot_top_level=True,
                )

                return user_stop_message(
                    "I stopped because an action failed.",
                    step_result.get("result", ""),
                )

        set_trace(
            stop_reason="Maximum iterative steps reached.",
            include_snapshot_top_level=True,
        )

        return user_stop_message(
            "I stopped because the task reached the maximum number of steps. Some work may have been completed, but the task may not be fully finished."
        )
