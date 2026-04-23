from pathlib import Path


class MemoryAgent:
    def __init__(self, max_items: int = 10):
        """
        Stores short-term conversational context for the current session.
        Also stores the last active file and its content.
        """
        self.max_items = max_items
        self.short_term: list[dict[str, str]] = []

        self.last_active_file_name = ""
        self.last_active_file_content = ""
        self.last_active_file_type = ""

        self.previous_active_file_name = ""
        self.previous_active_file_content = ""
        self.previous_active_file_type = ""

    def save_short_term(self, role: str, content: str) -> None:
        """
        Save a short-term memory entry.
        """
        cleaned_content = content.strip()

        debug_prefixes = (
            "[COORDINATOR DEBUG]",
            "[PLANNER DEBUG]",
            "[PLAN EXECUTOR DEBUG]",
            "[RESPONSE GENERATOR DEBUG]",
            "[REVIEWER DEBUG]",
            "[EXECUTOR DEBUG]",
        )

        if cleaned_content.startswith(debug_prefixes):
            return

        self.short_term.append({"role": role, "content": cleaned_content})

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
        Store the most recently active file and its content.
        """
        if self.last_active_file_name:
            self.previous_active_file_name = self.last_active_file_name
            self.previous_active_file_content = self.last_active_file_content
            self.previous_active_file_type = self.last_active_file_type

        self.last_active_file_name = filename
        self.last_active_file_content = content
        self.last_active_file_type = Path(filename).suffix.lower()

    def get_last_active_file_name(self) -> str:
        return self.last_active_file_name

    def get_last_active_file_content(self) -> str:
        return self.last_active_file_content

    def get_last_active_file_type(self) -> str:
        return self.last_active_file_type

    def get_previous_active_file_name(self) -> str:
        return self.previous_active_file_name

    def get_previous_active_file_content(self) -> str:
        return self.previous_active_file_content

    def get_previous_active_file_type(self) -> str:
        return self.previous_active_file_type

    def handle(self, action: str) -> str:
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

        if action == "get_last_active_file_type":
            return self.get_last_active_file_type()

        if action == "get_previous_active_file_name":
            return self.get_previous_active_file_name()

        if action == "get_previous_active_file_content":
            return self.get_previous_active_file_content()

        if action == "get_previous_active_file_type":
            return self.get_previous_active_file_type()

        return f"Memory could not find a supported action for '{action}'."