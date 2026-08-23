"""SQLite-backed job queue. One row per memo; state survives restarts."""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',
    engine TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    note_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as conn, conn:
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(self, job_id: str, engine: str, audio_path: str) -> None:
        now = _now()
        with closing(self._conn()) as conn, conn:
            conn.execute(
                "INSERT INTO jobs (id, status, engine, audio_path, created_at, updated_at) "
                "VALUES (?, 'queued', ?, ?, ?, ?)",
                (job_id, engine, audio_path, now, now),
            )

    def claim_next(self) -> sqlite3.Row | None:
        with closing(self._conn()) as conn, conn:
            return conn.execute(
                "UPDATE jobs SET status='processing', updated_at=? WHERE id = ("
                "  SELECT id FROM jobs WHERE status='queued' ORDER BY created_at, id LIMIT 1"
                ") RETURNING *",
                (_now(),),
            ).fetchone()

    def mark_done(self, job_id: str, note_path: str) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(
                "UPDATE jobs SET status='done', note_path=?, updated_at=? WHERE id=?",
                (note_path, _now(), job_id),
            )

    def mark_error(self, job_id: str, error: str) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(
                "UPDATE jobs SET status='error', error=?, updated_at=? WHERE id=?",
                (error[:2000], _now(), job_id),
            )

    def get(self, job_id: str) -> sqlite3.Row | None:
        with closing(self._conn()) as conn:
            return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()

    def recover_stale(self) -> int:
        """Requeue jobs left 'processing' by a crash/restart."""
        with closing(self._conn()) as conn, conn:
            return conn.execute(
                "UPDATE jobs SET status='queued', updated_at=? WHERE status='processing'",
                (_now(),),
            ).rowcount

    def counts(self) -> dict[str, int]:
        with closing(self._conn()) as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        return {row["status"]: row["n"] for row in rows}
