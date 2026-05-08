import agents.executor.tools as tools


class ExecutorAgent:
    """Dispatch low-level executor actions to concrete tools."""
    def __init__(self, memory=None, filesystem_guard=None, debug: bool = True):
        """Initialise the instance."""
        self.memory = memory
        self.filesystem_guard = filesystem_guard
        self.debug = debug

    
    def _debug(self, label: str, value) -> None:
        """Print a debug message when debug logging is enabled."""
        if self.debug:
            print(f"[EXECUTOR DEBUG] {label}: {value}")

    
    def _handle_list_input_files(self) -> str:
        """Return the visible uploaded input files."""
        files = tools.list_input_files()

        if not files:
            return "There are no files in the input directory."

        return "Available files:\n" + "\n".join(files)
    

    def _remember_file_if_valid(self, file_name: str, file_content: str) -> None:
        """Store a successfully read file as active memory."""
        if self.memory is None:
            return

        if not file_name.strip():
            return

        if file_content.startswith("Error:") or file_content.startswith("Warning:") or file_content.startswith("Access denied"):
            return

        self.memory.set_last_active_file(file_name, file_content)


    def _handle_read_file(self, action_input: str, original_prompt: str) -> str:
        """Resolve and read an uploaded/input file.

        Resolution order:
        1. Exact filename match against ``media_input/``.
        2. Single-file fallback when ``media_input/`` contains exactly one
           plausible file for this prompt (delegated to ``get_single_obvious_file``).
        3. Otherwise ask the user to specify which file.

        Phrase-based follow-ups such as "read it" or "the other file" are
        handled by the planner, which routes them to memory actions.
        """
        if action_input and action_input != "NONE":
            file_path = tools.find_file_in_input(action_input)
            self._debug("Explicit file match", file_path)

            if file_path is not None:
                file_content = tools.read_file(file_path)
                self._remember_file_if_valid(file_path.name, file_content)
                return file_content

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

    def _handle_read_multiple_files(self, action_input: str) -> str:
        """Read a comma-separated set of uploaded/input files."""
        filenames = [
            name.strip()
            for name in action_input.split(",")
            if name.strip()
        ]

        if not filenames:
            return "Error: read_multiple_files requires at least one filename."

        return tools.read_multiple_files(filenames)
    

    def _remember_viewed_workspace_file(self, action_input: str, result: str) -> None:
        """Store a successfully viewed workspace file as active memory."""
        if self.memory is None:
            return

        if result.startswith("Error:") or result.startswith("Access denied") or result.startswith("Warning:"):
            return

        file_name = action_input.strip()

        if "::" in file_name:
            file_name = file_name.split("::", 1)[0].strip()

        if not file_name:
            return

        self.memory.set_last_active_file(file_name, result)


    def handle(self, action: str, action_input: str = "", original_prompt: str = "") -> str:
        """Dispatch an executor action to the matching tool and return its result."""
        action = action.strip()
        action_input = action_input or ""
        original_prompt = original_prompt or ""

        if action == "get_current_time":
            return f"The current time is {tools.get_current_time()}."

        if action == "list_input_files":
            return self._handle_list_input_files()

        if action == "read_file":
            return self._handle_read_file(action_input, original_prompt)

        if action == "read_multiple_files":
            return self._handle_read_multiple_files(action_input)

        workspace_actions = {
            "view_file": tools.view_guarded_file,
            "create_file": tools.create_guarded_file,
            "write_file": tools.write_guarded_file,
            "append_file": tools.append_guarded_file,
            "delete_file": tools.delete_guarded_file,
            "delete_directory": tools.delete_directory,
            "edit_file": tools.prepare_guarded_edit_file,
            "find_file": tools.find_guarded_file,
            "list_directory": tools.list_directory,
            "create_directory": tools.create_directory,
            "move_path": tools.move_path,
            "move_directory_contents": tools.move_directory_contents,
            "copy_path": tools.copy_path,
            "rename_path": tools.rename_path,
            "run_python_file": tools.run_python_file,
        }

        tool_function = workspace_actions.get(action)

        if tool_function is None:
            return f"Executor could not find a supported action for '{action}'."

        result = tool_function(action_input, self.filesystem_guard)

        if action == "view_file":
            self._remember_viewed_workspace_file(action_input, result)

        return result
