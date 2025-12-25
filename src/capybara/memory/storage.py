"""SQLite persistence for conversation sessions."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite


class ConversationStorage:
    """SQLite-based conversation persistence."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or (Path.home() / ".capybara" / "conversations.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database schema (public API)."""
        await self._init_db()

    async def _init_db(self) -> None:
        """Initialize database schema (internal)."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    model TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    created_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id)
            """)
            await db.commit()
        self._initialized = True

    async def create_session(
        self,
        session_id: str,
        model: str,
        title: Optional[str] = None,
    ) -> None:
        """Create a new conversation session."""
        await self._init_db()
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, title or "Untitled", model, now, now),
            )
            await db.commit()

    async def save_message(
        self,
        session_id: str,
        message: dict[str, Any],
    ) -> None:
        """Save a message to a session."""
        await self._init_db()
        now = datetime.now(timezone.utc).isoformat()

        tool_calls = message.get("tool_calls")
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO messages
                   (session_id, role, content, tool_calls, tool_call_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    message.get("role"),
                    message.get("content"),
                    tool_calls_json,
                    message.get("tool_call_id"),
                    now,
                ),
            )
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            await db.commit()

    async def load_session(self, session_id: str) -> list[dict[str, Any]]:
        """Load all messages from a session."""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT role, content, tool_calls, tool_call_id FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
            rows = await cursor.fetchall()

        messages = []
        for row in rows:
            msg: dict[str, Any] = {"role": row["role"]}
            if row["content"]:
                msg["content"] = row["content"]
            if row["tool_calls"]:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            if row["tool_call_id"]:
                msg["tool_call_id"] = row["tool_call_id"]
            messages.append(msg)

        return messages

    async def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent sessions."""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, title, model, created_at, updated_at
                   FROM sessions ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and its messages."""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()

    async def update_session_title(self, session_id: str, title: str) -> None:
        """Update a session's title."""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
            await db.commit()
