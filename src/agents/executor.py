from tools import get_current_time, list_directory, read_file


class ExecutorAgent:
    def __init__(self, memory=None):
        self.memory = memory

    def handle(self, prompt: str) -> str:
        lower_prompt = prompt.lower()

        # NOTE: This is a very basic implementation just to demonstrate the concept.
        if "current time" in lower_prompt or "record the current time" in lower_prompt or "what is the time" in lower_prompt:
            timezone_name = "UTC"

            if self.memory is not None:
                stored_timezone = self.memory.get_fact("timezone")
                if stored_timezone:
                    timezone_name = stored_timezone

            return f"The current time is {get_current_time(timezone_name)}."

        if "list files" in lower_prompt or "list directory" in lower_prompt:
            return list_directory()

        return "Executor could not find a supported action for this task yet."