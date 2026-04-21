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
            "Then answer these fields strictly in this exact format:\n"
            "PLAN: <your structured plan>\n"
            "MEMORY: YES/NO\n"
            "EXECUTOR: YES/NO\n"
            "REVIEW: YES/NO\n"
            "MEMORY_ACTION: <memory action or NONE>\n"
            "MEMORY_INPUT: <memory input or NONE>\n"
            "ACTION: <tool name or NONE>\n"
            "INPUT: <tool input or NONE>\n\n"
            "Available executor actions are along with their rules:\n"
            "- get_current_time - If no executor action is needed, set ACTION to NONE and INPUT to NONE\n"
            "- list_input_files - If the user asks to list available files, use this action\n"
            "- read_file - If the user asks to read a specific file, use this action and provide the filename in INPUT\n"
            "Available memory actions are along with their rules:\n"
            "- get_first_user_prompt - If the user asks about the first thing they asked\n"
            "- get_last_user_prompt - If the user asks about the last thing they asked\n"
            "- get_short_term_context - If the user asks about the recent context\n\n"
            "Other Rules:\n"
            "- If no memory action is needed, set MEMORY_ACTION to NONE and MEMORY_INPUT to NONE.\n"
            "- If no executor action is needed, set ACTION to NONE and INPUT to NONE."
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
            "needs_review": False,
            "executor_action": "NONE",
            "executor_input": "NONE",
            "memory_action": "NONE",
            "memory_input": "NONE",
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
            elif upper_line.startswith("ACTION:"):
                result["executor_action"] = line.split(":", 1)[1].strip()
            elif upper_line.startswith("INPUT:"):
                result["executor_input"] = line.split(":", 1)[1].strip()
            elif upper_line.startswith("MEMORY_ACTION:"):
                result["memory_action"] = line.split(":", 1)[1].strip()
            elif upper_line.startswith("MEMORY_INPUT:"):
                result["memory_input"] = line.split(":", 1)[1].strip()

        return result


    def handle(self, prompt: str) -> str:
        """
        Main Planner entry point.
        """
        plan = self.create_plan(prompt)

        context = ""
        execution_result = ""

        if plan["needs_memory"] and self.memory is not None:
            context = self.memory.handle(
                plan["memory_action"],
                plan["memory_input"]
            )

        if plan["needs_executor"] and self.executor is not None:
            execution_result = self.executor.handle(
                plan["executor_action"],
                plan["executor_input"]
        )

        combined_result = (
            f"Plan:\n{plan['plan_text']}\n\n"
            f"Relevant context:\n{context if context else 'None'}\n\n"
            f"Execution result:\n{execution_result if execution_result else 'None'}"
        )

        if plan["needs_review"] and self.reviewer is not None:
            return self.reviewer.handle(prompt, combined_result)

        if execution_result and context:
            return f"{context}\n{execution_result}"

        if execution_result:
            return execution_result

        if context:
            return context

        return f"Generated plan:\n\n{plan['plan_text']}"
            