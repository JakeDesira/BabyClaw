import json
import re

from ollama_client import OllamaClient
import prompts


class MemoryWriter:
    def __init__(self, model: str | None = None, reasoning_settings=None, debug: bool = True):
        """
        Extracts durable long-term memories from the user's message.

        This does not store memories directly.
        It only decides what should be saved.
        """
        self.reasoning_settings = reasoning_settings
        self.client = OllamaClient(model=model)
        self.debug = debug


    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[MEMORY WRITER DEBUG] {label}: {value}")


    def _extract_json(self, text: str) -> dict:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end == -1 or end <= start:
            return {
                "should_save": False,
                "memories": [],
                "reason": "No JSON object found."
            }

        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as e:
            return {
                "should_save": False,
                "memories": [],
                "reason": f"Invalid JSON: {e}"
            }


    def _looks_like_memory_save_request(self, user_prompt: str) -> bool:
        """
        Cheap pre-check to avoid calling the memory writer LLM unless the user
        clearly asks to save something.
        """
        lower_prompt = user_prompt.lower().strip()

        if not lower_prompt:
            return False

        save_markers = [
            "remember",
            "remeber",
            "save this",
            "save that",
            "save my",
            "store this",
            "store that",
            "store my",
            "note this",
            "note that",
            "note my",
            "keep in mind",
            "from now on",
            "going forward",
            "for future reference",
            "don't forget",
            "do not forget",
        ]

        return any(marker in lower_prompt for marker in save_markers)


    def _normalise_extracted_memories(self, parsed: dict) -> list[dict]:
        memories = parsed.get("memories", [])

        if not isinstance(memories, list):
            return []

        cleaned_memories = []

        for item in memories:
            if not isinstance(item, dict):
                continue

            content = str(item.get("content", "")).strip()

            if not content:
                continue

            memory_type = str(item.get("memory_type", "general")).strip() or "general"

            try:
                importance = int(item.get("importance", 1))
            except (ValueError, TypeError):
                importance = 1

            importance = max(1, min(5, importance))

            cleaned_memories.append(
                {
                    "content": content,
                    "memory_type": memory_type,
                    "importance": importance,
                }
            )

        return cleaned_memories


    def extract(self, user_prompt: str, short_term_context: str = "") -> dict:
        """
        Return extracted memory candidates.

        Expected output:
        {
            "should_save": true,
            "memories": [
                {
                    "content": "User's name is Jake.",
                    "memory_type": "user_info",
                    "importance": 5
                }
            ],
            "reason": "The user explicitly asked to remember this."
        }
        """
        if not self._looks_like_memory_save_request(user_prompt):
            normalised = {
                "should_save": False,
                "memories": [],
                "reason": "Skipped memory writing because no save-memory wording was detected.",
            }

            self._debug("RULE-BASED MEMORY WRITER RESULT", normalised)
            return normalised

        user_message = (
            f"Recent conversation context:\n{short_term_context}\n\n"
            f"User request:\n{user_prompt}"
        )

        result = self.client.ask(
            prompt=user_message,
            system_prompt=prompts.memory_writer_prompt,
            temperature=0,
            think=self.reasoning_settings.memory_think if self.reasoning_settings else "low",
        )

        if not result.ok:
            self._debug("MEMORY WRITER ERROR", result.error)

            return {
                "should_save": False,
                "memories": [],
                "reason": result.error or "Memory writer failed."
            }

        self._debug("RAW MEMORY WRITER RESULT", result.content)

        parsed = self._extract_json(result.content)
        cleaned_memories = self._normalise_extracted_memories(parsed)

        normalised = {
            "should_save": bool(parsed.get("should_save", False)) and bool(cleaned_memories),
            "memories": cleaned_memories,
            "reason": str(parsed.get("reason", "")).strip(),
        }

        self._debug("PARSED MEMORY WRITER RESULT", normalised)

        return normalised