import tools


class ExecutorAgent:
    def __init__(self, memory=None):
        self.memory = memory

    def handle(self, action: str, action_input: str = "") -> str:
        if action == "get_current_time":
            return f"The current time is {tools.get_current_time()}."

        if action == "list_input_files":
            files = tools.list_input_files()
            if not files:
                return "There are no files in the input directory."
            return "Available files:\n" + "\n".join(files)

        if action == "read_file":
            if not action_input or action_input == "NONE":
                return "Error: No filename was provided."

            file_path = tools.find_file_in_input(action_input)
            if file_path is None:
                return f"Error: Could not find '{action_input}' in the input directory."

            return tools.read_file(file_path)

        return f"Executor could not find a supported action for '{action}'."