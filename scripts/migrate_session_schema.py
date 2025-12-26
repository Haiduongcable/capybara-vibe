"""Migration script to add parent_id and agent_mode columns."""

import asyncio
import aiosqlite
from pathlib import Path


async def migrate():
    """Migrate database schema for multi-agent delegation."""
    db_path = Path.home() / ".capybara" / "conversations.db"

    if not db_path.exists():
        print("⚠️  No existing database found. New schema will be created on first use.")
        return

    async with aiosqlite.connect(db_path) as db:
        # Check if columns exist
        cursor = await db.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in await cursor.fetchall()]

        if "parent_id" not in columns:
            await db.execute("ALTER TABLE sessions ADD COLUMN parent_id TEXT DEFAULT NULL")
            print("✅ Added parent_id column")
        else:
            print("ℹ️  parent_id column already exists")

        if "agent_mode" not in columns:
            await db.execute("ALTER TABLE sessions ADD COLUMN agent_mode TEXT DEFAULT 'parent'")
            print("✅ Added agent_mode column")
        else:
            print("ℹ️  agent_mode column already exists")

        # Create index
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_id)")
        print("✅ Created/verified idx_sessions_parent index")

        # Create events table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS session_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                tool_name TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)
        print("✅ Created/verified session_events table")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON session_events(session_id, created_at)")
        print("✅ Created/verified idx_events_session index")

        await db.commit()
        print("\n🎉 Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())
