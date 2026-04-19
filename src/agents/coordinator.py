from ollama_client import OllamaClient


class CoordinatorAgent:
    def __init__(self, planner=None, memory=None, model: str | None = None):
        """
        Entry point of the Baby Claw architecture.

        The Coordinator decides whether a request is simple enough to answer
        directly or whether it should be delegated to the Planner Agent.
        """
        self.client = OllamaClient(model=model)
        self.planner = planner
        self.memory = memory

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

    def is_simple_question(self, prompt: str) -> bool:
        """
        Use the model to classify whether the user request is a simple question
        or a more complex task that needs planning.
        """
        short_term_context = self._get_short_term_context()

        classifier_system_prompt = (
            "You are a routing assistant for a multi-agent AI system.\n"
            "Your task is to classify the user's request.\n"
            "Reply with only one word:\n"
            "- SIMPLE -> if the request can be answered directly without planning, tools, or multi-step reasoning\n"
            "- COMPLEX -> if the request needs planning, memory retrieval, file handling, or tool execution"
        )

        classifier_user_prompt = (
            f"Recent context:\n{short_term_context}\n\n"
            f"User request:\n{prompt}"
        )

        result = self.client.ask(
            prompt=classifier_user_prompt,
            system_prompt=classifier_system_prompt,
            temperature=0.1
        ).strip().upper()

        return result.startswith("SIMPLE")

    def handle(self, prompt: str) -> str:
        """
        Main routing method for the Coordinator Agent.
        """
        if self.memory is not None:
            try:
                self.memory.save_short_term(role="user", content=prompt)
            except AttributeError:
                pass

        if self.is_simple_question(prompt):
            response = self.client.ask(prompt, temperature=0.2)

        else:
            if self.planner is None:
                response = (
                    "This task appears to require planning, "
                    "but the Planner Agent has not been connected yet."
                )
            else:
                response = self.planner.handle(prompt)

        if self.memory is not None:
            try:
                self.memory.save_short_term(role="assistant", content=response)
            except AttributeError:
                pass

        return response