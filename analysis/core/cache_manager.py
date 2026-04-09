import sqlite3
import json
import dataclasses
from typing import Optional
from core.data_model import PaperRecord

# ---------------------------------------------------------------------------
# SubStageCache — per-title durability for M1 keyword extraction and M3
# classification.  Both tables live in the same llm_cache.sqlite as CacheDB
# so the single file holds all intermediate state.
# ---------------------------------------------------------------------------


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


class SubStageCache:
    """Per-title sub-stage caches for keyword extraction and classification.

    Stores results in the same llm_cache.sqlite as CacheDB so one file
    captures all intermediate state.  Each table uses a composite
    PRIMARY KEY (category, key) so different CCF categories never collide.

    Granularity: one row per title, written immediately after each batch is
    parsed.  A crash loses at most one in-flight batch (~50 titles), not the
    entire module's work.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS kw_results "
                "(category INTEGER NOT NULL, title_norm TEXT NOT NULL, "
                " keywords TEXT NOT NULL, "
                " PRIMARY KEY (category, title_norm))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS clf_results "
                "(category INTEGER NOT NULL, title TEXT NOT NULL, "
                " research_type TEXT NOT NULL, "
                " application_domain TEXT NOT NULL, "
                " PRIMARY KEY (category, title))"
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Keyword results
    # ------------------------------------------------------------------

    def save_kw_batch(self, category: int, title_norm_to_keywords: dict):
        """Persist one parsed keyword batch; called immediately after parsing."""
        rows = [
            (category, tn, json.dumps(kws, ensure_ascii=False))
            for tn, kws in title_norm_to_keywords.items()
        ]
        if not rows:
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO kw_results "
                "(category, title_norm, keywords) VALUES (?, ?, ?)",
                rows,
            )
            conn.commit()

    def load_kw_results(self, category: int) -> dict:
        """Return {title_norm: list[str]} for all persisted keyword rows."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT title_norm, keywords FROM kw_results WHERE category=?",
                (category,),
            ).fetchall()
        return {tn: json.loads(kws) for tn, kws in rows}

    def clear_kw_results(self, category: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM kw_results WHERE category=?", (category,))
            conn.commit()

    # ------------------------------------------------------------------
    # Classification results
    # ------------------------------------------------------------------

    def save_clf_batch(self, category: int, results: list):
        """Persist one parsed classification batch; called immediately after parsing.

        Each element must have: title, research_type, application_domain.
        """
        rows = [
            (
                category,
                r["title"],
                r.get("research_type", ""),
                json.dumps(r.get("application_domain", []), ensure_ascii=False),
            )
            for r in results
        ]
        if not rows:
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO clf_results "
                "(category, title, research_type, application_domain) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    def load_clf_results(self, category: int) -> dict:
        """Return {title: {"research_type": str, "application_domain": list}}."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT title, research_type, application_domain "
                "FROM clf_results WHERE category=?",
                (category,),
            ).fetchall()
        return {
            title: {
                "research_type": rt,
                "application_domain": json.loads(ad),
            }
            for title, rt, ad in rows
        }

    def clear_clf_results(self, category: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM clf_results WHERE category=?", (category,))
            conn.commit()
