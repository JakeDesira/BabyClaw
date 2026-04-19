from ollama_client import OllamaClient


class PlannerAgent:
    def __init__(self, memory=None, executor=None, reviewer=None, model: str | None = None):
        """
        The Planner Agent handles complex tasks by breaking them into
        smaller subtasks and deciding which other agents are needed.
        """
        self.client = OllamaClient(model=model, supports_think=True)
        self.memory = memory
        self.executor = executor
        self.reviewer = reviewer

    def _get_context(self) -> str:
        """
        Retrieve relevant context from memory if available.
        """
        if self.memory is None:
            return ""

        try:
            return self.memory.get_short_term_context()
        except AttributeError:
            return ""

    def create_plan(self, prompt: str) -> dict:
        """
        Ask the model to break the task into smaller steps and indicate
        which other agents may be required.
        """
        planner_system_prompt = (
            "You are the Planner Agent in a lightweight multi-agent AI system.\n"
            "Break the user's request into clear subtasks.\n"
            "Then answer these three questions strictly with YES or NO:\n"
            "1. Does this task need memory/context retrieval?\n"
            "2. Does this task need executor/tool use?\n"
            "3. Does this task need review/checking?\n\n"
            "Return your answer in this exact format:\n"
            "PLAN: <your structured plan>\n"
            "MEMORY: YES/NO\n"
            "EXECUTOR: YES/NO\n"
            "REVIEW: YES/NO"
        )

        context = self._get_context()

        planner_user_prompt = (
            f"Recent context:\n{context}\n\n"
            f"User request:\n{prompt}"
        )

        raw_plan = self.client.ask(
            prompt=planner_user_prompt,
            system_prompt=planner_system_prompt,
            temperature=0.2,
            think="medium"
        )
    
        return self._parse_plan(raw_plan)
    
    def _parse_plan(self, raw_plan: str) -> dict:
        """
        Parse the planner output into a structured dictionary.        
        """

        result = {
            "plan_text": raw_plan,
            "needs_memory": False,
            "needs_executor": False,
            "needs_review": False
        }

        for line in raw_plan.splitlines():
            upper_line = line.strip().upper()

            if upper_line.startswith("MEMORY:"):
                result["needs_memory"] = "YES" in upper_line
            elif upper_line.startswith("EXECUTOR:"):
                result["needs_executor"] = "YES" in upper_line
            elif upper_line.startswith("REVIEW:"):
                result["needs_review"] = "YES" in upper_line
            elif upper_line.startswith("PLAN:"):
                result["plan_text"] = line.split(":", 1)[1].strip()

        return result

    def handle(self, prompt: str) -> str:
        """
        Main Planner entry point.
        """
        plan = self.create_plan(prompt)

        return (
            f"Generated plan:\n{plan['plan_text']}\n\n"
            f"Needs memory: {plan['needs_memory']}\n"
            f"Needs executor: {plan['needs_executor']}\n"
            f"Needs review: {plan['needs_review']}"
        )
    