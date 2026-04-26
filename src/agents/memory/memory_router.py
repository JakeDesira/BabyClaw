import json
import re

from ollama_client import OllamaClient
import prompts


class MemoryRouter:
    def __init__(self, model: str | None = None, reasoning_settings=None, debug: bool = True):
        """
        Decides whether the current user request would benefit from
        long-term memory retrieval.

        This does not answer the user.
        It only decides:
        - should memory be searched?
        - what query should be used?
        """
        self.reasoning_settings = reasoning_settings
        self.client = OllamaClient(model=model, supports_think=True)
        self.debug = debug


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[MEMORY ROUTER DEBUG] {label}: {value}")


    def _extract_json(self, text: str) -> dict:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end == -1 or end <= start:
            return {
                "needs_memory": False,
                "search_query": "",
                "reason": "No JSON object found."
            }

        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as e:
            return {
                "needs_memory": False,
                "search_query": "",
                "reason": f"Invalid JSON: {e}"
            }


    def _looks_like_memory_request(self, user_prompt: str) -> bool:
        """
        Cheap pre-check to avoid calling the memory router LLM for prompts
        that clearly do not need long-term memory.
        """
        lower_prompt = user_prompt.lower().strip()

        if not lower_prompt:
            return False

        memory_markers = [
            "remember",
            "remeber",
            "save this",
            "save that",
            "store this",
            "store that",
            "note this",
            "note that",
            "keep in mind",
            "what do you remember",
            "what have you saved",
            "saved memories",
            "long-term memory",
            "what is my",
            "what's my",
            "who am i",
            "my name",
            "my email",
            "my project",
            "my preference",
            "my preferences",
            "my saved",
            "saved path",
            "saved paths",
            "accessible path",
            "accessible paths",
            "previously",
            "last time",
            "from before",
            "do you know my",
            "use my information",
            "my information",
            "my details",
            "my saved information",
            "about me",
        ]

        if any(marker in lower_prompt for marker in memory_markers):
            return True

        follow_up_markers = [
            "it",
            "that",
            "this",
            "the other",
            "same as before",
        ]

        personalised_markers = [
            "my",
            "me",
            "i usually",
            "i prefer",
        ]

        return (
            any(marker in lower_prompt for marker in follow_up_markers)
            and any(marker in lower_prompt for marker in personalised_markers)
        )


    def _looks_like_file_or_code_task(self, user_prompt: str) -> bool:
        """
        Avoid memory lookup for obvious filesystem/code tasks.
        These should be handled by the planner/executor instead.
        """
        lower_prompt = user_prompt.lower()

        file_task_markers = [
            "file",
            "folder",
            "directory",
            "path",
            "workspace",
            "approved directory",
            "create",
            "delete",
            "rename",
            "move",
            "copy",
            "append",
            "write",
            "edit",
            "fix",
            "run",
            "traceback",
            "error:",
            ".py",
            ".txt",
            ".pdf",
            ".json",
        ]

        return any(marker in lower_prompt for marker in file_task_markers)


    def check(self, user_prompt: str, short_term_context: str = "") -> dict:
        cleaned_prompt = user_prompt.strip()

        if not cleaned_prompt:
            return {
                "needs_memory": False,
                "search_query": "",
                "reason": "Empty prompt.",
            }

        user_message = (
            f"Recent conversation context:\n{short_term_context if short_term_context else 'None'}\n\n"
            f"User request:\n{cleaned_prompt}"
        )

        result = self.client.ask(
            prompt=user_message,
            system_prompt=prompts.memory_router_prompt,
            temperature=0,
            think=self.reasoning_settings.memory_think if self.reasoning_settings else "low",
        )

        if not result.ok:
            self._debug("MEMORY ROUTER ERROR", result.error)

            return {
                "needs_memory": False,
                "search_query": "",
                "reason": result.error or "Memory router failed.",
            }

        self._debug("RAW MEMORY ROUTER RESULT", result.content)

        decision = self._extract_json(result.content)

        needs_memory = bool(decision.get("needs_memory", False))
        search_query = str(decision.get("search_query", "")).strip()
        reason = str(decision.get("reason", "")).strip()

        if needs_memory and not search_query:
            search_query = cleaned_prompt

        normalised = {
            "needs_memory": needs_memory,
            "search_query": search_query,
            "reason": reason,
        }

        self._debug("PARSED MEMORY ROUTER RESULT", normalised)

        return normalised