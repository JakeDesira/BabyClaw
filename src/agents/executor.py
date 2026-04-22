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
            lower_prompt = original_prompt.lower().strip()

            # 1. Explicit filename first
            if action_input and action_input != "NONE":
                file_path = tools.find_file_in_input(action_input)
                #
                print(f"[EXECUTOR DEBUG] Explicit file match: {file_path}")
                if file_path is not None:
                    file_content = tools.read_file(file_path)

                    if (
                        self.memory is not None
                        and not file_content.startswith("Error:")
                        and not file_content.startswith("Warning:")
                    ):
                        self.memory.set_last_active_file(file_path.name, file_content)

                    return file_content

            # 2. Follow-up references to currently active file
            if self.memory is not None:
                last_file_name = self.memory.get_last_active_file_name()
                last_file_content = self.memory.get_last_active_file_content()
                #
                print(f"[EXECUTOR DEBUG] Active file candidate: {last_file_name}")

                current_file_phrases = {
                    "read it",
                    "read the file",
                    "open it",
                    "open the file",
                    "show it",
                    "show the file",
                    "process it",
                    "summarise it",
                    "summarize it",
                    "explain it",
                    "what does it say",
                    "what does the file say",
                }

                if lower_prompt in current_file_phrases and last_file_name and last_file_content:
                    print(f"[EXECUTOR DEBUG] Actually reusing active file: {last_file_name}")
                    return last_file_content

            # 3. "Other file" support
            if self.memory is not None:
                previous_file_name = self.memory.get_previous_active_file_name()
                previous_file_content = self.memory.get_previous_active_file_content()

                if "other file" in lower_prompt and previous_file_name and previous_file_content:
                    #
                    print(f"[EXECUTOR DEBUG] Switching to previous file: {previous_file_name}")
                    # Promote previous to active when user explicitly switches to it
                    self.memory.set_last_active_file(previous_file_name, previous_file_content)
                    return previous_file_content

            # 4. Deterministic obvious-file fallback
            obvious_file = tools.get_single_obvious_file(original_prompt)
            if obvious_file is not None:
                #
                print(f"[EXECUTOR DEBUG] Obvious file fallback: {obvious_file}")
                file_content = tools.read_file(obvious_file)

                if (
                    self.memory is not None
                    and not file_content.startswith("Error:")
                    and not file_content.startswith("Warning:")
                ):
                    self.memory.set_last_active_file(obvious_file.name, file_content)

                return file_content

            # 5. Final clarification
            #
            print("[EXECUTOR DEBUG] Could not resolve file, asking user to specify")
            files = tools.list_input_files()
            if not files:
                return "There are no files in the input directory."

            return "Please specify which file to read. Available files:\n" + "\n".join(files)
        
        if action == "read_multiple_files":
            filenames = [f.strip() for f in action_input.split(",") if f.strip() and f.strip() != "NONE"]
            
            if not filenames:
                return "No filenames provided for read_multiple_files."

            results = []
            last_found_path = None

            for name in filenames:
                path = tools.find_file_in_input(name)
                print(f"[EXECUTOR DEBUG] Multi-file match for '{name}': {path}")
                if path is not None:
                    content = tools.read_file(path)
                    results.append(f"=== {path.name} ===\n{content}")
                    if (
                        self.memory is not None
                        and not content.startswith("Error:")
                        and not content.startswith("Warning:")
                    ):
                        self.memory.set_last_active_file(path.name, content)
                    last_found_path = path
                else:
                    results.append(f"=== {name} ===\nError: File not found.")

            return "\n\n".join(results) if results else "None of the specified files could be found."

        return f"Executor could not find a supported action for '{action}'."