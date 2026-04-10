import sqlite3
import json
from typing import Optional


class CacheDB:
    """SQLite-backed key-value cache for LLM prompt responses."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS kv "
                "(key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.commit()

    def get(self, key: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM kv WHERE key=?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()

    def invalidate(self, key: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM kv WHERE key=?", (key,))
            conn.commit()
