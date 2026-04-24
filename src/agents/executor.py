import tools


class ExecutorAgent:
    def __init__(self, memory=None, filesystem_guard=None, debug: bool = True):
        self.memory = memory
        self.filesystem_guard = filesystem_guard
        self.debug = debug

    
    def _debug(self, label: str, value) -> None:
        if self.debug:
            print(f"[EXECUTOR DEBUG] {label}: {value}")

    
    def _handle_list_input_files(self) -> str:
        files = tools.list_input_files()

        if not files:
            return "There are no files in the input directory."

        return "Available files:\n" + "\n".join(files)
    

    def _remember_file_if_valid(self, file_name: str, file_content: str) -> None:
        if self.memory is None:
            return

        if file_content.startswith("Error:") or file_content.startswith("Warning:"):
            return

        self.memory.set_last_active_file(file_name, file_content)


    def _try_get_active_file_content(self, lower_prompt: str) -> str | None:
        if self.memory is None:
            return None

        last_file_name = self.memory.get_last_active_file_name()
        last_file_content = self.memory.get_last_active_file_content()
        self._debug("Active file candidate", last_file_name)

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
            self._debug("Actually reusing active file", last_file_name)
            return last_file_content

        return None
    

    def _try_get_previous_file_content(self, lower_prompt: str) -> str | None:
        if self.memory is None:
            return None

        previous_file_name = self.memory.get_previous_active_file_name()
        previous_file_content = self.memory.get_previous_active_file_content()

        if "other file" in lower_prompt and previous_file_name and previous_file_content:
            self._debug("Switching to previous file", previous_file_name)
            self.memory.set_last_active_file(previous_file_name, previous_file_content)
            return previous_file_content

        return None


    def _handle_read_file(self, action_input: str, original_prompt: str) -> str:
        lower_prompt = original_prompt.lower().strip()

        if action_input and action_input != "NONE":
            file_path = tools.find_file_in_input(action_input)
            self._debug("Explicit file match", file_path)

            if file_path is not None:
                file_content = tools.read_file(file_path)
                self._remember_file_if_valid(file_path.name, file_content)
                return file_content

        active_file_content = self._try_get_active_file_content(lower_prompt)

        if active_file_content is not None:
            return active_file_content

        previous_file_content = self._try_get_previous_file_content(lower_prompt)

        if previous_file_content is not None:
            return previous_file_content

        obvious_file = tools.get_single_obvious_file(original_prompt)

        if obvious_file is not None:
            self._debug("Obvious file fallback", obvious_file)
            file_content = tools.read_file(obvious_file)
            self._remember_file_if_valid(obvious_file.name, file_content)
            return file_content

        self._debug("Could not resolve file", "asking user to specify")

        files = tools.list_input_files()

        if not files:
            return "There are no files in the input directory."

        return "Please specify which file to read. Available files:\n" + "\n".join(files)


    def handle(self, action: str, action_input: str = "", original_prompt: str = "") -> str:
        if action == "get_current_time":
            return f"The current time is {tools.get_current_time()}."

        if action == "list_input_files":
            return self._handle_list_input_files()

        if action == "read_file":
            return self._handle_read_file(action_input, original_prompt)

        if action == "read_multiple_files":
            return self._handle_read_multiple_files(action_input)

        if action == "view_file":
            return tools.view_guarded_file(action_input, self.filesystem_guard)

        if action == "create_file":
            return tools.create_guarded_file(action_input, self.filesystem_guard)

        if action == "append_file":
            return tools.append_guarded_file(action_input, self.filesystem_guard)

        if action == "delete_file":
            return tools.delete_guarded_file(action_input, self.filesystem_guard)

        if action == "edit_file":
            return tools.prepare_guarded_edit_file(action_input, self.filesystem_guard)

        if action == "list_directory":
            return tools.list_directory(action_input, self.filesystem_guard)

        if action == "create_directory":
            return tools.create_directory(action_input, self.filesystem_guard)

        if action == "move_path":
            return tools.move_path(action_input, self.filesystem_guard)

        if action == "copy_path":
            return tools.copy_path(action_input, self.filesystem_guard)

        if action == "rename_path":
            return tools.rename_path(action_input, self.filesystem_guard)

        return f"Executor could not find a supported action for '{action}'."
