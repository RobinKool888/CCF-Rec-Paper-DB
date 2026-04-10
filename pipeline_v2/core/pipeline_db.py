import json
import sqlite3
import time
from typing import Optional


class PipelineDB:
    """
    Single SQLite file per venue. Stores all per-title and per-stage
    savepoint state. Path: output/{venue}/pipeline.sqlite

    Tables:
      m0_records       (title_norm TEXT PK, record_json TEXT)
      m1_keywords      (title_norm TEXT PK, keywords TEXT)       -- JSON list
      m1_canonical     (title_norm TEXT PK, canonical_terms TEXT) -- JSON list
      m1_anomaly       (title_norm TEXT PK, flag INTEGER, reason TEXT)
      m1_term_map      (venue TEXT PK, term_map_json TEXT)
      m3_tags          (title_norm TEXT PK, research_type TEXT, application_domain TEXT)
      m4_embeddings    (title_norm TEXT PK, embedding TEXT)      -- JSON list of floats
      stage_done       (key TEXT PK, ts REAL)                    -- key = "M0","M1","M2","M3","M4"
    """

    def __init__(self, db_path: str):
        import os
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self):
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS m0_records (
                    title_norm TEXT PRIMARY KEY, record_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS m1_keywords (
                    title_norm TEXT PRIMARY KEY, keywords TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS m1_canonical (
                    title_norm TEXT PRIMARY KEY, canonical_terms TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS m1_anomaly (
                    title_norm TEXT PRIMARY KEY, flag INTEGER NOT NULL, reason TEXT);
                CREATE TABLE IF NOT EXISTS m1_term_map (
                    venue TEXT PRIMARY KEY, term_map_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS m3_tags (
                    title_norm TEXT PRIMARY KEY,
                    research_type TEXT NOT NULL,
                    application_domain TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS m4_embeddings (
                    title_norm TEXT PRIMARY KEY, embedding TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS stage_done (
                    key TEXT PRIMARY KEY, ts REAL NOT NULL);
            """)

    # ── stage checkpoints ──────────────────────────────────────────────────

    def mark_stage_done(self, stage: str):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO stage_done (key,ts) VALUES (?,?)",
                      (stage, time.time()))

    def is_stage_done(self, stage: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT 1 FROM stage_done WHERE key=?", (stage,)).fetchone()
        return row is not None

    # ── M0 ────────────────────────────────────────────────────────────────

    def save_m0_record(self, title_norm: str, record_dict: dict):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO m0_records VALUES (?,?)",
                      (title_norm, json.dumps(record_dict, ensure_ascii=False)))

    def save_m0_records_bulk(self, records: list):
        """Save list of PaperRecord objects (as dicts) in one transaction."""
        import dataclasses
        rows = [(r.title_normalized, json.dumps(dataclasses.asdict(r), ensure_ascii=False))
                for r in records]
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO m0_records VALUES (?,?)", rows)

    def load_m0_records(self) -> list:
        """Return list of dicts (not PaperRecord — caller reconstructs)."""
        with self._conn() as c:
            rows = c.execute("SELECT record_json FROM m0_records").fetchall()
        return [json.loads(r[0]) for r in rows]

    def m0_title_norms(self) -> set:
        with self._conn() as c:
            rows = c.execute("SELECT title_norm FROM m0_records").fetchall()
        return {r[0] for r in rows}

    # ── M1 keywords ───────────────────────────────────────────────────────

    def save_m1_keywords_batch(self, batch: dict):
        """batch: {title_norm: [kw, ...]}"""
        rows = [(k, json.dumps(v)) for k, v in batch.items()]
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO m1_keywords VALUES (?,?)", rows)

    def load_m1_keywords(self) -> dict:
        """Returns {title_norm: [kw, ...]}"""
        with self._conn() as c:
            rows = c.execute("SELECT title_norm, keywords FROM m1_keywords").fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    def m1_keyword_done_norms(self) -> set:
        with self._conn() as c:
            rows = c.execute("SELECT title_norm FROM m1_keywords").fetchall()
        return {r[0] for r in rows}

    # ── M1 canonical terms ────────────────────────────────────────────────

    def save_m1_canonical_batch(self, batch: dict):
        """batch: {title_norm: [canonical_term, ...]}"""
        rows = [(k, json.dumps(v)) for k, v in batch.items()]
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO m1_canonical VALUES (?,?)", rows)

    def load_m1_canonical(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT title_norm, canonical_terms FROM m1_canonical").fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    # ── M1 anomaly ────────────────────────────────────────────────────────

    def save_m1_anomaly_batch(self, batch: list):
        """batch: list of {title_norm, flag (bool), reason (str)}"""
        rows = [(item["title_norm"], int(item["flag"]), item.get("reason", ""))
                for item in batch]
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO m1_anomaly VALUES (?,?,?)", rows)

    def load_m1_anomaly(self) -> dict:
        """Returns {title_norm: {flag: bool, reason: str}}"""
        with self._conn() as c:
            rows = c.execute("SELECT title_norm, flag, reason FROM m1_anomaly").fetchall()
        return {r[0]: {"flag": bool(r[1]), "reason": r[2]} for r in rows}

    def m1_anomaly_done_norms(self) -> set:
        with self._conn() as c:
            rows = c.execute("SELECT title_norm FROM m1_anomaly").fetchall()
        return {r[0] for r in rows}

    # ── M1 term map ───────────────────────────────────────────────────────

    def save_m1_term_map(self, venue: str, term_map: list):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO m1_term_map VALUES (?,?)",
                      (venue, json.dumps(term_map, ensure_ascii=False)))

    def load_m1_term_map(self, venue: str) -> Optional[list]:
        with self._conn() as c:
            row = c.execute("SELECT term_map_json FROM m1_term_map WHERE venue=?",
                            (venue,)).fetchone()
        return json.loads(row[0]) if row else None

    # ── M3 tags ───────────────────────────────────────────────────────────

    def save_m3_tags_batch(self, batch: list):
        """batch: list of {title_norm, research_type, application_domain (list)}"""
        rows = [(item["title_norm"], item["research_type"],
                 json.dumps(item["application_domain"]))
                for item in batch]
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO m3_tags VALUES (?,?,?)", rows)

    def load_m3_tags(self) -> dict:
        """Returns {title_norm: {research_type, application_domain}}"""
        with self._conn() as c:
            rows = c.execute(
                "SELECT title_norm, research_type, application_domain FROM m3_tags"
            ).fetchall()
        return {
            r[0]: {"research_type": r[1], "application_domain": json.loads(r[2])}
            for r in rows
        }

    def m3_done_norms(self) -> set:
        with self._conn() as c:
            rows = c.execute("SELECT title_norm FROM m3_tags").fetchall()
        return {r[0] for r in rows}

    # ── M4 embeddings ─────────────────────────────────────────────────────

    def save_m4_embeddings_batch(self, batch: dict):
        """batch: {title_norm: [float, ...]}"""
        rows = [(k, json.dumps(v)) for k, v in batch.items()]
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO m4_embeddings VALUES (?,?)", rows)

    def load_m4_embeddings(self) -> dict:
        """Returns {title_norm: [float, ...]}"""
        with self._conn() as c:
            rows = c.execute("SELECT title_norm, embedding FROM m4_embeddings").fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    def m4_done_norms(self) -> set:
        with self._conn() as c:
            rows = c.execute("SELECT title_norm FROM m4_embeddings").fetchall()
        return {r[0] for r in rows}

    # ── force restart ─────────────────────────────────────────────────────

    def clear_all(self):
        """Delete all rows from all tables. Does not drop the tables."""
        tables = [
            "m0_records", "m1_keywords", "m1_canonical", "m1_anomaly",
            "m1_term_map", "m3_tags", "m4_embeddings", "stage_done",
        ]
        with self._conn() as c:
            for table in tables:
                c.execute(f"DELETE FROM {table}")
