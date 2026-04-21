class MemoryAgent:
    def __init__(self, max_items: int = 10):
        """
        Stores short-term conversational context for the current session.
        Also stores the last active file and its content.
        """
        self.max_items = max_items
        self.short_term = []
        self.last_active_file_name = ""
        self.last_active_file_content = ""


    def save_short_term(self, role: str, content: str) -> None:
        """
        Save a short-term memory entry.
        """
        self.short_term.append({"role": role, "content": content})

        if len(self.short_term) > self.max_items:
            self.short_term = self.short_term[-self.max_items:]


    def get_short_term_context(self) -> str:
        """
        Return recent short-term context as formatted text.
        """
        if not self.short_term:
            return ""

        return "\n".join(
            f"{entry['role']}: {entry['content']}"
            for entry in self.short_term
        )


    def get_last_user_prompt(self) -> str:
        """
        Return the most recent user prompt.
        """
        for entry in reversed(self.short_term):
            if entry["role"] == "user":
                return entry["content"]

        return ""


    def get_first_user_prompt(self) -> str:
        """
        Return the first user prompt in short-term memory.
        """
        for entry in self.short_term:
            if entry["role"] == "user":
                return entry["content"]

        return ""


    def clear_short_term(self) -> None:
        """
        Clear short-term memory.
        """
        self.short_term.clear()


    def set_last_active_file(self, filename: str, content: str) -> None:
        """
        Store the most recently read file and its content.
        """
        self.last_active_file_name = filename
        self.last_active_file_content = content


    def get_last_active_file_name(self) -> str:
        """
        Return the filename of the most recently read file.
        """
        return self.last_active_file_name


    def get_last_active_file_content(self) -> str:
        """
        Return the content of the most recently read file.
        """
        return self.last_active_file_content


    def handle(self, action: str, action_input: str = "") -> str:
        """
        Handle memory-related actions.
        """
        if action == "get_first_user_prompt":
            return self.get_first_user_prompt()

        if action == "get_last_user_prompt":
            return self.get_last_user_prompt()

        if action == "get_short_term_context":
            return self.get_short_term_context()

        if action == "get_last_active_file_name":
            return self.get_last_active_file_name()

        if action == "get_last_active_file_content":
            return self.get_last_active_file_content()

        return f"Memory could not find a supported action for '{action}'."