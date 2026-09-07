"""SQLite storage for runs, so visibility can be compared over time."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    label TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    provider TEXT NOT NULL,
    model TEXT,
    prompt TEXT NOT NULL,
    text TEXT,
    citations TEXT,
    latency_ms INTEGER
);
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id INTEGER NOT NULL REFERENCES answers(id),
    brand TEXT NOT NULL,
    mentioned INTEGER NOT NULL,
    mention_count INTEGER NOT NULL,
    cited INTEGER NOT NULL,
    cited_urls TEXT,
    first_position INTEGER
);
CREATE INDEX IF NOT EXISTS idx_answers_run ON answers(run_id);
CREATE INDEX IF NOT EXISTS idx_det_answer ON detections(answer_id);
"""


class Store:
    def __init__(self, path: str | Path = "visibility.db"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def new_run(self, label: Optional[str] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, label) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), label),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def save_answer(self, run_id: int, answer, detections: Iterable) -> int:
        cur = self.conn.execute(
            "INSERT INTO answers (run_id, provider, model, prompt, text, citations, latency_ms) VALUES (?,?,?,?,?,?,?)",
            (run_id, answer.provider, answer.model, answer.prompt, answer.text, json.dumps(answer.citations), answer.latency_ms),
        )
        answer_id = int(cur.lastrowid)
        self.conn.executemany(
            "INSERT INTO detections (answer_id, brand, mentioned, mention_count, cited, cited_urls, first_position) VALUES (?,?,?,?,?,?,?)",
            [
                (answer_id, d.brand, int(d.mentioned), d.mention_count, int(d.cited), json.dumps(d.cited_urls), d.first_position)
                for d in detections
            ],
        )
        self.conn.commit()
        return answer_id

    def run_rows(self, run_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            """SELECT a.provider, a.prompt, d.brand, d.mentioned, d.mention_count, d.cited, d.cited_urls, d.first_position
               FROM detections d JOIN answers a ON a.id = d.answer_id WHERE a.run_id = ?""",
            (run_id,),
        ).fetchall()

    def previous_run_id(self, run_id: int, label: Optional[str] = None) -> Optional[int]:
        if label is not None:
            row = self.conn.execute(
                "SELECT id FROM runs WHERE id < ? AND label = ? ORDER BY id DESC LIMIT 1", (run_id, label)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT id FROM runs WHERE id < ? ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
        return int(row["id"]) if row else None

    def history(self, brand: str, provider: Optional[str] = None) -> List[dict]:
        """Per-run mention/citation rate for one brand — the time series."""
        q = """SELECT r.id AS run_id, r.started_at, a.provider,
                      AVG(d.mentioned) AS mention_rate, AVG(d.cited) AS citation_rate, COUNT(*) AS prompts
               FROM detections d JOIN answers a ON a.id = d.answer_id JOIN runs r ON r.id = a.run_id
               WHERE d.brand = ? {} GROUP BY r.id, a.provider ORDER BY r.id"""
        params: list = [brand]
        if provider:
            q = q.format("AND a.provider = ?")
            params.append(provider)
        else:
            q = q.format("")
        return [dict(r) for r in self.conn.execute(q, params).fetchall()]
