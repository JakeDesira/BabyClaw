from ollama_client import OllamaClient


class ReviewerAgent:
    def __init__(self, model: str | None = None):
        self.client = OllamaClient(model=model, supports_think=True)

    def handle(self, original_prompt: str, draft_result: str) -> str:
        review_system_prompt = (
            "You are the Reviewer Agent in a lightweight multi-agent AI system.\n"
            "Your task is to check whether the result is correct, complete, and clear.\n"
            "If needed, improve it slightly.\n"
            "Return only the improved final answer."
        )

        review_user_prompt = (
            f"Original user request:\n{original_prompt}\n\n"
            f"Draft result:\n{draft_result}"
        )

        return self.client.ask(prompt=review_user_prompt, system_prompt=review_system_prompt, temperature=0.1, think="high")