from ollama_client import OllamaClient
import re

class ReviewerAgent:
    def __init__(self, model: str | None = None):
        self.client = OllamaClient(model=model, supports_think=True)

    def review(self, original_prompt: str, draft_result: str) -> dict:
        review_system_prompt = (
            "You are the Reviewer Agent in a lightweight multi-agent AI system.\n"
            "Check whether the draft result fully satisfies the user's request.\n"
            "Return your answer strictly in this exact format:\n"
            "APPROVED: YES/NO\n"
            "FEEDBACK: <short feedback>\n\n"
            "Rules:\n"
            "- APPROVED should be YES only if the task is fully completed.\n"
            "- Short literal answers are acceptable when the question asks for a short literal output.\n"
            "- If the answer correctly gives the requested words, phrase, number, or extracted text, approve it.\n"
            "- If APPROVED is NO, FEEDBACK must clearly explain what still needs to be done.\n"
            "- Be concise."
        )

        review_user_prompt = (
            f"Original user request:\n{original_prompt}\n\n"
            f"Draft result:\n{draft_result}"
        )

        raw_review = self.client.ask(
            prompt=review_user_prompt,
            system_prompt=review_system_prompt,
            temperature=0,
            think="low"
        )

        #
        print(f"[REVIEWER DEBUG] RAW REVIEW: {raw_review}")
        parsed = self._parse_review(raw_review)
        print(f"[REVIEWER DEBUG] PARSED REVIEW: {parsed}")
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