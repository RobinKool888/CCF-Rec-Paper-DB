import sqlite3
import json
import dataclasses
from typing import Optional
from core.data_model import PaperRecord


class CacheDB:
    """SQLite-backed key-value cache."""

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


class PaperCache:
    """Persists PaperRecord lists to SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS papers "
                "(category INTEGER, data TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS mtimes "
                "(category INTEGER, data TEXT)"
            )
            conn.commit()

    def save_papers(self, records: list, category: int):
        serialized = json.dumps(
            [dataclasses.asdict(r) for r in records]
        )
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM papers WHERE category=?", (category,)
            )
            conn.execute(
                "INSERT INTO papers (category, data) VALUES (?, ?)",
                (category, serialized),
            )
            conn.commit()

    def load_papers(self, category: int) -> list:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM papers WHERE category=?", (category,)
            ).fetchone()
        if not row:
            return []
        raw = json.loads(row[0])
        return [PaperRecord(**r) for r in raw]

    def get_mtimes(self, category: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM mtimes WHERE category=?", (category,)
            ).fetchone()
        return json.loads(row[0]) if row else {}

    def save_mtimes(self, mtimes: dict, category: int):
        serialized = json.dumps(mtimes)
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM mtimes WHERE category=?", (category,)
            )
            conn.execute(
                "INSERT INTO mtimes (category, data) VALUES (?, ?)",
                (category, serialized),
            )
            conn.commit()
