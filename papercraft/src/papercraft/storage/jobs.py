"""SQLite job history plus immutable, revisioned artifact files."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel


JobStatus = Literal[
    "created",
    "document_ready",
    "analysis_ready",
    "evidence_ready",
    "poster_ready",
    "review_failed",
    "complete",
    "budget_paused",
    "model_paused",
    "failed",
]


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    paper_id: str
    title: str
    status: str
    spent_usd: str
    budget_limit_usd: str
    created_at: str
    updated_at: str
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = root / "papercraft.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    spent_usd TEXT NOT NULL DEFAULT '0',
                    budget_limit_usd TEXT NOT NULL DEFAULT '8.00',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    artifact_name TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, artifact_name, revision)
                );
                CREATE TABLE IF NOT EXISTS usage_records (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    call_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost_usd TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, call_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_job(
        self,
        *,
        job_id: str,
        paper_id: str,
        title: str,
        status: JobStatus = "created",
        budget_limit_usd: Decimal = Decimal("8.00"),
    ) -> JobRecord:
        now = _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, '0', ?, ?, ?, NULL)",
                (job_id, paper_id, title, status, str(budget_limit_usd), now, now),
            )
        (self.root / "jobs" / job_id).mkdir(parents=True, exist_ok=True)
        return self.get_job(job_id)

    def upsert_job(
        self,
        *,
        job_id: str,
        paper_id: str,
        title: str,
        status: JobStatus,
        budget_limit_usd: Decimal = Decimal("8.00"),
    ) -> JobRecord:
        now = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO jobs
                   (job_id, paper_id, title, status, spent_usd, budget_limit_usd, created_at, updated_at, error)
                   VALUES (?, ?, ?, ?, '0', ?, ?, ?, NULL)
                   ON CONFLICT(job_id) DO UPDATE SET
                     paper_id=excluded.paper_id, title=excluded.title,
                     status=excluded.status, updated_at=excluded.updated_at, error=NULL""",
                (job_id, paper_id, title, status, str(budget_limit_usd), now, now),
            )
        (self.root / "jobs" / job_id).mkdir(parents=True, exist_ok=True)
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
        shutil.rmtree(self.root / "jobs" / job_id, ignore_errors=True)

    def get_job(self, job_id: str) -> JobRecord:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return JobRecord(**dict(row))

    def list_jobs(self) -> list[JobRecord]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
        return [JobRecord(**dict(row)) for row in rows]

    def update_status(
        self, job_id: str, status: JobStatus, *, error: str | None = None
    ) -> JobRecord:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE jobs SET status=?, error=?, updated_at=? WHERE job_id=?",
                (status, error, _now(), job_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)
        self.add_event(job_id, "status", {"status": status, "error": error})
        return self.get_job(job_id)

    def add_event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
                (job_id, event_type, json.dumps(payload, ensure_ascii=False), _now()),
            )

    def record_artifact(
        self, job_id: str, artifact_name: str, revision: int, relative_path: str
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?,?)",
                (job_id, artifact_name, revision, relative_path, _now()),
            )

    def latest_artifact_path(self, job_id: str, artifact_name: str) -> Path:
        with self._connect() as db:
            row = db.execute(
                """SELECT relative_path FROM artifacts
                   WHERE job_id=? AND artifact_name=? ORDER BY revision DESC LIMIT 1""",
                (job_id, artifact_name),
            ).fetchone()
        if row is None:
            raise KeyError(f"{job_id}/{artifact_name}")
        return self.root / row["relative_path"]

    def record_usage(self, job_id: str, record: Any) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO usage_records VALUES(?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    record.call_id,
                    record.provider,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    str(record.cost_usd),
                    _now(),
                ),
            )
            spent = db.execute(
                "SELECT cost_usd FROM usage_records WHERE job_id=?", (job_id,)
            ).fetchall()
            total = sum((Decimal(row["cost_usd"]) for row in spent), Decimal("0"))
            db.execute(
                "UPDATE jobs SET spent_usd=?, updated_at=? WHERE job_id=?",
                (str(total), _now(), job_id),
            )

    def usage_rows(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM usage_records WHERE job_id=? ORDER BY created_at", (job_id,)
            ).fetchall()
        return [dict(row) for row in rows]


class ArtifactRepository:
    model_types: dict[str, type[BaseModel]]
    required_artifact_names = (
        "document_ir",
        "paper_analysis",
        "evidence_graph",
        "poster_plan",
        "review_result",
    )
    optional_artifact_names = ("narrative_plan", "visual_plan")

    def __init__(self, store: JobStore) -> None:
        from papercraft.models import (
            DocumentIR,
            EvidenceGraph,
            NarrativePlan,
            PaperAnalysis,
            PosterPlan,
            ReviewResult,
            VisualPlan,
        )

        self.store = store
        self.model_types = {
            "document_ir": DocumentIR,
            "paper_analysis": PaperAnalysis,
            "evidence_graph": EvidenceGraph,
            "narrative_plan": NarrativePlan,
            "visual_plan": VisualPlan,
            "poster_plan": PosterPlan,
            "review_result": ReviewResult,
        }

    def job_dir(self, job_id: str) -> Path:
        path = self.store.root / "jobs" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save(self, job_id: str, artifact_name: str, value: BaseModel) -> Path:
        if artifact_name not in self.model_types:
            raise ValueError(f"unknown artifact: {artifact_name}")
        revision = int(getattr(value, "artifact_revision"))
        artifact_dir = self.job_dir(job_id) / "artifacts" / artifact_name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / f"r{revision:04d}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        relative = path.relative_to(self.store.root).as_posix()
        self.store.record_artifact(job_id, artifact_name, revision, relative)
        return path

    def load(self, job_id: str, artifact_name: str) -> BaseModel:
        model_type = self.model_types[artifact_name]
        path = self.store.latest_artifact_path(job_id, artifact_name)
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def has(self, job_id: str, artifact_name: str) -> bool:
        try:
            self.store.latest_artifact_path(job_id, artifact_name)
        except KeyError:
            return False
        return True

    def bundle(self, job_id: str) -> dict[str, Any]:
        bundle = {
            name: self.load(job_id, name).model_dump(mode="json")
            for name in self.required_artifact_names
        }
        bundle.update(
            {
                name: self.load(job_id, name).model_dump(mode="json")
                for name in self.optional_artifact_names
                if self.has(job_id, name)
            }
        )
        return bundle


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
