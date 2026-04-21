import tools


class ExecutorAgent:
    def __init__(self, memory=None):
        self.memory = memory

    def handle(self, action: str, action_input: str = "", original_prompt: str = "") -> str:
        if action == "get_current_time":
            return f"The current time is {tools.get_current_time()}."

        if action == "list_input_files":
            files = tools.list_input_files()
            if not files:
                return "There are no files in the input directory."
            return "Available files:\n" + "\n".join(files)

        if action == "read_file":
            # 1. Try explicit action_input first
            if action_input and action_input != "NONE":
                file_path = tools.find_file_in_input(action_input)
                if file_path is not None:
                    file_content = tools.read_file(file_path)

                    if (
                        self.memory is not None
                        and not file_content.startswith("Error:")
                        and not file_content.startswith("Warning:")
                    ):
                        self.memory.set_last_active_file(file_path.name, file_content)

                    return file_content

            # 2. If the user refers vaguely to the previously active file, reuse it
            if self.memory is not None:
                last_file_name = self.memory.get_last_active_file_name()
                last_file_content = self.memory.get_last_active_file_content()

                vague_prompt = original_prompt.lower().strip()
                vague_phrases = {
                    "read the file",
                    "read it",
                    "open it",
                    "open the file",
                    "process it",
                    "summarise it",
                    "summarize it",
                    "explain it",
                    "what does it say",
                    "what does the file say",
                }

                if vague_prompt in vague_phrases and last_file_name and last_file_content:
                    return last_file_content

            # 3. Deterministic fallback: choose a single obvious file
            obvious_file = tools.get_single_obvious_file(original_prompt)
            if obvious_file is not None:
                file_content = tools.read_file(obvious_file)

                if (
                    self.memory is not None
                    and not file_content.startswith("Error:")
                    and not file_content.startswith("Warning:")
                ):
                    self.memory.set_last_active_file(obvious_file.name, file_content)

                return file_content

            # 4. Final fallback: ask user to choose
            files = tools.list_input_files()
            if not files:
                return "There are no files in the input directory."

            return "Please specify which file to read. Available files:\n" + "\n".join(files)

        return f"Executor could not find a supported action for '{action}'."