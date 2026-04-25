import json
import re

from ollama_client import OllamaClient
import prompts


class MemoryWriter:
    def __init__(self, model: str | None = None, debug: bool = True):
        """
        Extracts durable long-term memories from the user's message.

        This does not store memories directly.
        It only decides what should be saved.
        """
        self.client = OllamaClient(model=model, supports_think=True)
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
        user_message = (
            f"Recent conversation context:\n{short_term_context}\n\n"
            f"User request:\n{user_prompt}"
        )

        result = self.client.ask(
            prompt=user_message,
            system_prompt=prompts.memory_writer_prompt,
            temperature=0,
            think="low",
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

        memories = parsed.get("memories", [])

        if not isinstance(memories, list):
            memories = []

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
            except ValueError:
                importance = 1

            importance = max(1, min(5, importance))

            cleaned_memories.append(
                {
                    "content": content,
                    "memory_type": memory_type,
                    "importance": importance,
                }
            )

        normalised = {
            "should_save": bool(parsed.get("should_save", False)) and bool(cleaned_memories),
            "memories": cleaned_memories,
            "reason": str(parsed.get("reason", "")).strip(),
        }

        self._debug("PARSED MEMORY WRITER RESULT", normalised)

        return normalised