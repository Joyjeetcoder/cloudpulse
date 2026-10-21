"""Single-process SQLite storage and durable work queue, on a local disk."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "cloudpulse.db"

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                  id INTEGER PRIMARY KEY, repository TEXT NOT NULL,
                  run_id INTEGER NOT NULL, run_attempt INTEGER NOT NULL,
                  run_number INTEGER, workflow_name TEXT NOT NULL DEFAULT '',
                  branch TEXT NOT NULL DEFAULT '', commit_sha TEXT NOT NULL DEFAULT '',
                  github_url TEXT NOT NULL, conclusion TEXT NOT NULL,
                  created_at TEXT, completed_at TEXT, duration_seconds REAL,
                  state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                  next_attempt_at REAL NOT NULL DEFAULT 0,
                  analysis_json TEXT, excerpt_json TEXT, jobs_json TEXT,
                  error TEXT, model TEXT, usage_json TEXT, log_note TEXT,
                  inserted_at REAL NOT NULL, updated_at REAL NOT NULL,
                  UNIQUE(repository, run_id, run_attempt)
                );
                CREATE INDEX IF NOT EXISTS runs_queue ON runs(state, next_attempt_at);
                CREATE TABLE IF NOT EXISTS deliveries (
                  delivery_id TEXT PRIMARY KEY, received_at REAL NOT NULL
                );
                PRAGMA user_version=1;
            """)
            # Only one server process is supported; recover interrupted jobs on restart.
            con.execute("UPDATE runs SET state='pending', next_attempt_at=0 WHERE state='processing'")
            con.execute("DELETE FROM deliveries WHERE received_at < ?", (time.time() - 30*86400,))

    def enqueue(self, repository: str, run: dict, delivery_id: str | None = None) -> tuple[int, bool]:
        now = time.time()
        values = (
            repository.lower(), int(run["id"]), int(run.get("run_attempt", 1)),
            run.get("run_number"), str(run.get("name") or "Workflow")[:200],
            str(run.get("head_branch") or "")[:200], str(run.get("head_sha") or "")[:64],
            f"https://github.com/{repository}/actions/runs/{int(run['id'])}",
            str(run.get("conclusion") or "unknown")[:50], run.get("run_started_at") or run.get("created_at"),
            run.get("updated_at"), now, now,
        )
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            duplicate_delivery = False
            if delivery_id:
                cur = con.execute("INSERT OR IGNORE INTO deliveries VALUES (?, ?)", (delivery_id, now))
                duplicate_delivery = cur.rowcount == 0
            cur = con.execute("""INSERT OR IGNORE INTO runs
                (repository,run_id,run_attempt,run_number,workflow_name,branch,commit_sha,
                 github_url,conclusion,created_at,completed_at,inserted_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            inserted = cur.rowcount == 1
            row = con.execute("SELECT id FROM runs WHERE repository=? AND run_id=? AND run_attempt=?",
                              values[:3]).fetchone()
            return row["id"], inserted and not duplicate_delivery

    def claim(self) -> dict | None:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("""SELECT * FROM runs WHERE state='pending' AND next_attempt_at <= ?
                               ORDER BY inserted_at LIMIT 1""", (time.time(),)).fetchone()
            if row is None:
                return None
            con.execute("UPDATE runs SET state='processing', attempts=attempts+1, updated_at=? WHERE id=?",
                        (time.time(), row["id"]))
            item = dict(row)
            item["attempts"] += 1
            return item

    def update(self, run_id: int, **fields):
        allowed = {"state", "error", "analysis_json", "excerpt_json", "jobs_json", "model",
                   "usage_json", "log_note", "next_attempt_at", "duration_seconds", "conclusion",
                   "workflow_name", "branch", "commit_sha", "created_at", "completed_at"}
        if not fields or not set(fields).issubset(allowed):
            raise ValueError("Invalid database update")
        fields["updated_at"] = time.time()
        with self.connect() as con:
            con.execute("UPDATE runs SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?",
                        (*fields.values(), run_id))

    @staticmethod
    def decode(row) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        for name in ("analysis", "excerpt", "jobs", "usage"):
            raw = item.pop(name + "_json", None)
            item[name] = json.loads(raw) if raw else None
        return item

    def get(self, run_id: int) -> dict | None:
        with self.connect() as con:
            return self.decode(con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())

    def list(self, limit=50, offset=0, conclusion=None) -> dict:
        where, args = (" WHERE conclusion=?", [conclusion]) if conclusion else ("", [])
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM runs" + where, args).fetchone()[0]
            rows = con.execute("""SELECT id,repository,run_id,run_attempt,run_number,workflow_name,
                branch,commit_sha,github_url,conclusion,created_at,completed_at,duration_seconds,
                state,attempts,error,inserted_at,updated_at FROM runs""" + where +
                " ORDER BY inserted_at DESC LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
            return {"items": [dict(r) for r in rows], "total": total}

    def retry(self, run_id: int) -> bool:
        with self.connect() as con:
            cur = con.execute("""UPDATE runs SET state='pending', attempts=0, next_attempt_at=0,
                error=NULL, analysis_json=NULL, updated_at=? WHERE id=?
                AND state IN ('error','inconclusive','completed')""", (time.time(), run_id))
            return cur.rowcount == 1

    def stats(self) -> dict:
        with self.connect() as con:
            row = con.execute("""SELECT COUNT(*) total,
                COALESCE(SUM(conclusion='success'),0) successful,
                COALESCE(SUM(conclusion IN ('failure','timed_out','startup_failure')),0) failed,
                COALESCE(SUM(state IN ('pending','processing')),0) processing FROM runs""").fetchone()
            return dict(row)
