class MemoryAgent:
    def __init__(self, max_items: int = 10):
        """
        Stores short-term conversational context for the current session.
        """
        self.max_items = max_items
        self.short_term = []
        self.facts = {} 

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
        for entry in reversed(self.short_term):
            if entry["role"] == "user":
                return entry["content"]
            
        return ""

    def get_first_user_prompt(self) -> str:
        for entry in self.short_term:
            if entry["role"] == "user":
                return entry["content"]
        return ""
    
    def set_fact(self, key: str, value: str) -> None:
        """
        Store a simple user fact.
        """
        self.facts[key] = value

    def get_fact(self, key: str) -> str:
        """
        Retrieve a stored user fact.
        """
        return self.facts.get(key, "")

    def clear_short_term(self) -> None:
        """
        Clear short-term memory.
        """
        self.short_term.clear()