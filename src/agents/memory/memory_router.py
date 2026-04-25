import json
import re

from ollama_client import OllamaClient
import prompts


class MemoryRouter:
    def __init__(self, model: str | None = None, debug: bool = True):
        """
        Decides whether the current user request would benefit from
        long-term memory retrieval.

        This does not answer the user.
        It only decides:
        - should memory be searched?
        - what query should be used?
        """
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


    def check(self, user_prompt: str, short_term_context: str = "") -> dict:
        user_message = (
            f"Recent conversation context:\n{short_term_context}\n\n"
            f"User request:\n{user_prompt}"
        )

        result = self.client.ask(
            prompt=user_message,
            system_prompt=prompts.memory_router_prompt,
            temperature=0,
            think="low",
        )

        if not result.ok:
            self._debug("MEMORY ROUTER ERROR", result.error)

            return {
                "needs_memory": False,
                "search_query": "",
                "reason": result.error or "Memory router failed."
            }

        self._debug("RAW MEMORY ROUTER RESULT", result.content)

        decision = self._extract_json(result.content)

        needs_memory = bool(decision.get("needs_memory", False))
        search_query = str(decision.get("search_query", "")).strip()
        reason = str(decision.get("reason", "")).strip()

        if needs_memory and not search_query:
            search_query = user_prompt

        normalised = {
            "needs_memory": needs_memory,
            "search_query": search_query,
            "reason": reason,
        }

        self._debug("PARSED MEMORY ROUTER RESULT", normalised)

        return normalised