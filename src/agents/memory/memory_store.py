import sqlite3
from pathlib import Path
from datetime import datetime


class SQLiteMemoryStore:
    def __init__(self, db_path: str | Path = "babyclaw_memory.db"):
        """
        SQLite-backed long-term memory store.

        This class is responsible only for database storage and retrieval.
        It should not contain LLM logic.
        """
        self.db_path = Path(db_path)
        self._ensure_database()


    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


    def _ensure_database(self) -> None:
        """
        Create the memories table if it does not already exist.
        """
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'conversation',
                    importance INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT
                )
                """
            )

            connection.commit()


    def add_memory(self, content: str, memory_type: str = "general", source: str = "conversation", importance: int = 1) -> int:
        """
        Add a new long-term memory.

        Returns the ID of the inserted memory.
        """
        cleaned_content = content.strip()
        cleaned_type = memory_type.strip() or "general"
        cleaned_source = source.strip() or "conversation"

        if not cleaned_content:
            raise ValueError("Cannot save an empty memory.")

        now = datetime.now().isoformat(timespec="seconds")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (
                    memory_type,
                    content,
                    source,
                    importance,
                    created_at,
                    last_accessed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cleaned_type,
                    cleaned_content,
                    cleaned_source,
                    importance,
                    now,
                    None,
                ),
            )

            connection.commit()
            return int(cursor.lastrowid)


    def search_memories(self, query: str, limit: int = 5) -> list[dict]:
        """
        Search long-term memories using simple keyword matching.

        This searches both the full phrase and individual words, making it more
        forgiving for queries like 'user name' vs 'user's name'.
        """
        cleaned_query = query.strip()

        if not cleaned_query:
            return []

        words = [
            word.strip().lower()
            for word in cleaned_query.replace("'", " ").split()
            if word.strip()
        ]

        now = datetime.now().isoformat(timespec="seconds")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    memory_type,
                    content,
                    source,
                    importance,
                    created_at,
                    last_accessed_at
                FROM memories
                ORDER BY importance DESC, created_at DESC
                LIMIT 100
                """
            ).fetchall()

            scored_rows = []

            for row in rows:
                searchable_text = " ".join(
                    [
                        str(row["memory_type"]),
                        str(row["content"]),
                        str(row["source"]),
                    ]
                ).lower().replace("'", " ")

                score = 0

                if cleaned_query.lower() in searchable_text:
                    score += 5

                for word in words:
                    if word in searchable_text:
                        score += 1

                if score > 0:
                    scored_rows.append((score, row))

            scored_rows.sort(
                key=lambda item: (
                    item[0],
                    item[1]["importance"],
                    item[1]["created_at"],
                ),
                reverse=True,
            )

            selected_rows = [row for _, row in scored_rows[:limit]]
            memory_ids = [row["id"] for row in selected_rows]

            if memory_ids:
                placeholders = ",".join("?" for _ in memory_ids)

                connection.execute(
                    f"""
                    UPDATE memories
                    SET last_accessed_at = ?
                    WHERE id IN ({placeholders})
                    """,
                    [now, *memory_ids],
                )

                connection.commit()

            return [dict(row) for row in selected_rows]


    def list_recent_memories(self, limit: int = 10) -> list[dict]:
        """
        Return the most recently created memories.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    memory_type,
                    content,
                    source,
                    importance,
                    created_at,
                    last_accessed_at
                FROM memories
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]


    def get_memory(self, memory_id: int) -> dict | None:
        """
        Retrieve one memory by ID.
        """
        now = datetime.now().isoformat(timespec="seconds")

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    memory_type,
                    content,
                    source,
                    importance,
                    created_at,
                    last_accessed_at
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()

            if row is None:
                return None

            connection.execute(
                """
                UPDATE memories
                SET last_accessed_at = ?
                WHERE id = ?
                """,
                (now, memory_id),
            )

            connection.commit()

            return dict(row)


    def delete_memory(self, memory_id: int) -> bool:
        """
        Delete one memory by ID.

        Returns True if a memory was deleted.
        """
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            )

            connection.commit()
            return cursor.rowcount > 0


    def clear_memories(self) -> int:
        """
        Delete all memories.

        Returns the number of deleted rows.
        """
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM memories
                """
            )

            connection.commit()
            return cursor.rowcount


    def format_memories(self, memories: list[dict]) -> str:
        """
        Format memories into readable text for the MemoryAgent or LLM context.
        """
        if not memories:
            return "No matching long-term memories found."

        lines = []

        for memory in memories:
            lines.append(
                f"[{memory['id']}] "
                f"({memory['memory_type']}, importance {memory['importance']}) "
                f"{memory['content']}"
            )

        return "\n".join(lines)