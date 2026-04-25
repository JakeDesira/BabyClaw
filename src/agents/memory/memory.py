from pathlib import Path

from .memory_store import SQLiteMemoryStore


class MemoryAgent:
    def __init__(self, max_items: int = 10, memory_store: SQLiteMemoryStore | None = None):
        """
        Stores short-term conversational context for the current session.
        Also stores active file context and long-term memory through SQLite.
        """
        self.max_items = max_items
        self.short_term: list[dict[str, str]] = []

        self.last_active_file_name = ""
        self.last_active_file_content = ""
        self.last_active_file_type = ""

        self.previous_active_file_name = ""
        self.previous_active_file_content = ""
        self.previous_active_file_type = ""

        self.memory_store = memory_store or SQLiteMemoryStore()


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
            "[MEMORY ROUTER DEBUG]",
            "[MEMORY WRITER DEBUG]",
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


    # ===== LONG-TERM MEMORY ======

    def save_long_term_memory(self, content: str, memory_type: str = "general", source: str = "conversation", importance: int = 1) -> str:
        """
        Save a general long-term memory in SQLite.
        """
        try:
            memory_id = self.memory_store.add_memory(
                content=content,
                memory_type=memory_type,
                source=source,
                importance=importance,
            )

            return f"Saved long-term memory [{memory_id}]: {content}"

        except Exception as e:
            return f"Error saving long-term memory: {e}"
        

    def save_long_term_memory_if_new(self, content: str, memory_type: str = "general", source: str = "conversation", importance: int = 1) -> str:
        """
        Save a long-term memory only if the exact same content does not already exist.
        """
        cleaned_content = content.strip()

        if not cleaned_content:
            return "Error: Cannot save an empty memory."

        existing = self.memory_store.search_memories(
            query=cleaned_content,
            limit=20,
        )

        for memory in existing:
            if (
                memory.get("memory_type") == memory_type
                and memory.get("content") == cleaned_content
            ):
                return f"Memory already exists [{memory['id']}]: {cleaned_content}"

        return self.save_long_term_memory(
            content=cleaned_content,
            memory_type=memory_type,
            source=source,
            importance=importance,
        )


    def search_long_term_memory(self, query: str, limit: int = 5, include_paths: bool = False) -> str:
        """
        Search long-term memory using the SQLite memory store.
        """
        memories = self.memory_store.search_memories(query=query, limit=limit)

        if not include_paths:
            memories = [
                memory
                for memory in memories
                if memory.get("memory_type") != "accessible_path"
            ]

        return self.memory_store.format_memories(memories)


    def list_recent_long_term_memories(self, limit: int = 10) -> str:
        """
        Return recent long-term memories.
        """
        memories = self.memory_store.list_recent_memories(limit=limit)
        return self.memory_store.format_memories(memories)


    def delete_long_term_memory(self, memory_id_text: str) -> str:
        """
        Delete a long-term memory by ID.
        """
        try:
            memory_id = int(memory_id_text.strip())
        except ValueError:
            return "Error: delete_long_term_memory requires a numeric memory ID."

        deleted = self.memory_store.delete_memory(memory_id)

        if deleted:
            return f"Deleted long-term memory [{memory_id}]."

        return f"No long-term memory found with ID [{memory_id}]."


    # ===== SAVED ACCESSIBLE PATHS =====

    def save_accessible_path(self, path_text: str) -> str:
        """
        Save an approved accessible path in long-term memory.

        This does not approve the path by itself.
        FilesystemGuard still controls live access.
        """
        cleaned_path = path_text.strip().strip("\"'")

        if not cleaned_path:
            return "Error: No path provided."

        resolved_path = str(Path(cleaned_path).expanduser().resolve())

        existing = self.memory_store.search_memories(
            query=resolved_path,
            limit=20,
        )

        for memory in existing:
            if (
                memory.get("memory_type") == "accessible_path"
                and memory.get("content") == resolved_path
            ):
                return f"Accessible path is already saved: {resolved_path}"

        try:
            memory_id = self.memory_store.add_memory(
                content=resolved_path,
                memory_type="accessible_path",
                source="filesystem_guard",
                importance=5,
            )

            return f"Saved accessible path [{memory_id}]: {resolved_path}"

        except Exception as e:
            return f"Error saving accessible path: {e}"


    def list_accessible_paths(self) -> str:
        """
        List saved accessible paths.
        """
        memories = self.memory_store.search_memories(
            query="accessible_path",
            limit=100,
        )

        paths = [
            memory
            for memory in memories
            if memory.get("memory_type") == "accessible_path"
        ]

        if not paths:
            return "No accessible paths are saved."

        return "Saved accessible paths:\n" + "\n".join(
            f"[{memory['id']}] {memory['content']}"
            for memory in paths
        )


    def find_accessible_path(self, path_text: str) -> dict | None:
        """
        Find a saved accessible path by exact resolved path.
        """
        cleaned_path = path_text.strip().strip("\"'")

        if not cleaned_path:
            return None

        resolved_path = str(Path(cleaned_path).expanduser().resolve())

        memories = self.memory_store.search_memories(
            query=resolved_path,
            limit=100,
        )

        for memory in memories:
            if (
                memory.get("memory_type") == "accessible_path"
                and memory.get("content") == resolved_path
            ):
                return memory

        return None


    def revoke_accessible_path(self, path_text: str) -> str:
        """
        Remove a saved accessible path from long-term memory.

        This only removes it from SQLite memory.
        FilesystemGuard should also revoke it from the live approved list.
        """
        memory = self.find_accessible_path(path_text)

        if memory is None:
            return f"No saved accessible path found for: {path_text}"

        deleted = self.memory_store.delete_memory(int(memory["id"]))

        if deleted:
            return f"Revoked saved accessible path: {memory['content']}"

        return f"Could not revoke saved accessible path: {path_text}"


    def get_saved_accessible_path_values(self) -> list[str]:
        """
        Return saved accessible paths as a plain list of path strings.

        Useful for restoring approved paths when the program starts.
        """
        memories = self.memory_store.search_memories(
            query="accessible_path",
            limit=100,
        )

        return [
            memory["content"]
            for memory in memories
            if memory.get("memory_type") == "accessible_path"
        ]


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

        if action == "get_last_active_file_type":
            return self.get_last_active_file_type()

        if action == "get_previous_active_file_name":
            return self.get_previous_active_file_name()

        if action == "get_previous_active_file_content":
            return self.get_previous_active_file_content()

        if action == "get_previous_active_file_type":
            return self.get_previous_active_file_type()

        if action == "search_long_term_memory":
            return self.search_long_term_memory(action_input)

        if action == "list_recent_long_term_memories":
            return self.list_recent_long_term_memories()

        if action == "delete_long_term_memory":
            return self.delete_long_term_memory(action_input)

        if action == "save_accessible_path":
            return self.save_accessible_path(action_input)

        if action == "list_accessible_paths":
            return self.list_accessible_paths()

        if action == "revoke_accessible_path":
            return self.revoke_accessible_path(action_input)

        return f"Memory could not find a supported action for '{action}'."