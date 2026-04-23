import re

from ollama_client import OllamaClient
import prompts


class ReviewerAgent:
    def __init__(self, model: str | None = None, debug: bool = True):
        self.client = OllamaClient(model=model, supports_think=True)
        self.debug = debug

    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[REVIEWER DEBUG] {label}: {value}")

    def review(self, original_prompt: str, draft_result: str) -> dict:
        review_user_prompt = (
            f"Original user request:\n{original_prompt}\n\n"
            f"Draft result:\n{draft_result}"
        )

        raw_review = self.client.ask(
            prompt=review_user_prompt,
            system_prompt=prompts.reviewer_prompt,
            temperature=0,
            think="low"
        )

        self._debug("RAW REVIEW", raw_review)
        parsed = self._parse_review(raw_review)
        self._debug("PARSED REVIEW", parsed)
        return parsed

    def _parse_review(self, raw_review: str) -> dict:
        cleaned = re.sub(r"<think>.*?</think>", "", raw_review, flags=re.DOTALL).strip()

        result = {
            "approved": False,
            "feedback": cleaned
        }

        for line in cleaned.splitlines():
            upper_line = line.strip().upper()

            if upper_line.startswith("APPROVED:"):
                result["approved"] = "YES" in upper_line

            elif upper_line.startswith("FEEDBACK:"):
                result["feedback"] = line.split(":", 1)[1].strip()

        return result