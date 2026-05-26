from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from crucible.modules.optimizer.domain.models import OptimizationRun


class RunSummary(BaseModel):
    id: str
    run_mode: str = "optimize"
    status: str
    stop_reason: str | None
    best_score: float | None
    best_version: int | None
    total_cost_usd: float
    iterations_count: int
    target_model: str
    reasoning_model: str
    started_at: str
    ended_at: str | None


class TaskRecord(BaseModel):
    id: str
    status: str
    run_id: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    created_at: str
    updated_at: str


class FileRunStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_run(self, run: OptimizationRun) -> None:
        run_dir = self._run_dir(run.id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
        if run.best_iteration is not None:
            (run_dir / "best_prompt.txt").write_text(
                run.best_iteration.prompt.template,
                encoding="utf-8",
            )
            (run_dir / "report.json").write_text(
                json.dumps(
                    {
                        "run_id": run.id,
                        "status": run.status,
                        "stop_reason": run.stop_reason,
                        "best_version": run.best_iteration.version,
                        "best_score": run.best_iteration.score,
                        "total_cost_usd": run.total_cost_usd,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    async def save_iteration(self, run: OptimizationRun) -> None:
        run_dir = self._run_dir(run.id)
        run_dir.mkdir(parents=True, exist_ok=True)
        iteration = run.iterations[-1]
        with (run_dir / "iterations.jsonl").open("a", encoding="utf-8") as file:
            file.write(iteration.model_dump_json() + "\n")
        with (run_dir / "verdicts.jsonl").open("a", encoding="utf-8") as file:
            for verdict in iteration.verdicts:
                file.write(verdict.model_dump_json() + "\n")
        await self.save_run(run)

    async def load_run(self, run_id: str) -> OptimizationRun:
        path = self._run_dir(run_id) / "run.json"
        return OptimizationRun.model_validate_json(path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(path.name for path in self.root.iterdir() if path.is_dir())

    def _run_dir(self, run_id: str) -> Path:
        return self.root / run_id


class SQLiteRunStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    async def save_run(self, run: OptimizationRun) -> None:
        summary = _summary(run)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, run_mode, status, stop_reason, best_score, best_version, total_cost_usd,
                    iterations_count, target_model, reasoning_model, started_at, ended_at, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_mode=excluded.run_mode,
                    status=excluded.status,
                    stop_reason=excluded.stop_reason,
                    best_score=excluded.best_score,
                    best_version=excluded.best_version,
                    total_cost_usd=excluded.total_cost_usd,
                    iterations_count=excluded.iterations_count,
                    target_model=excluded.target_model,
                    reasoning_model=excluded.reasoning_model,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    payload=excluded.payload
                """,
                (
                    summary.id,
                    summary.run_mode,
                    summary.status,
                    summary.stop_reason,
                    summary.best_score,
                    summary.best_version,
                    summary.total_cost_usd,
                    summary.iterations_count,
                    summary.target_model,
                    summary.reasoning_model,
                    summary.started_at,
                    summary.ended_at,
                    run.model_dump_json(),
                ),
            )
            conn.execute("DELETE FROM iterations WHERE run_id = ?", (run.id,))
            conn.execute("DELETE FROM verdicts WHERE run_id = ?", (run.id,))
            for iteration in run.iterations:
                conn.execute(
                    """
                    INSERT INTO iterations (
                        run_id, version, prompt_hash, score, pass_rate,
                        total_cost_usd, started_at, ended_at, payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.id,
                        iteration.version,
                        iteration.prompt.content_hash,
                        iteration.score,
                        iteration.score_report.pass_rate,
                        iteration.score_report.operational.total_cost_usd,
                        iteration.timestamp_started.isoformat(),
                        iteration.timestamp_ended.isoformat(),
                        iteration.model_dump_json(),
                    ),
                )
                for verdict in iteration.verdicts:
                    conn.execute(
                        """
                        INSERT INTO verdicts (
                            run_id, iteration_version, test_case_id, score, passed,
                            latency_ms, tokens_in, tokens_out, cost_usd, tags, payload
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run.id,
                            iteration.version,
                            verdict.test_case.id,
                            verdict.score,
                            int(verdict.passed),
                            verdict.execution.latency_ms,
                            verdict.execution.tokens_in,
                            verdict.execution.tokens_out,
                            verdict.execution.cost_usd,
                            json.dumps(verdict.test_case.tags),
                            verdict.model_dump_json(),
                        ),
                    )

    async def save_iteration(self, run: OptimizationRun) -> None:
        await self.save_run(run)

    async def load_run(self, run_id: str) -> OptimizationRun:
        if run_id == "latest":
            run_id = self.latest_run_id()
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"Run '{run_id}' not found")
        return OptimizationRun.model_validate_json(row["payload"])

    def list_runs(self, limit: int | None = None) -> list[RunSummary]:
        query = "SELECT * FROM runs ORDER BY started_at DESC"
        params: tuple[int, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [RunSummary.model_validate(dict(row)) for row in rows]

    def latest_run_id(self) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if row is None:
            raise FileNotFoundError("No runs found")
        return str(row["id"])

    def verdict_payloads(self, run_id: str, iteration_version: int | None = None) -> list[dict]:
        query = "SELECT payload FROM verdicts WHERE run_id = ?"
        params: tuple[object, ...] = (run_id,)
        if iteration_version is not None:
            query += " AND iteration_version = ?"
            params = (run_id, iteration_version)
        query += " ORDER BY iteration_version, test_case_id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def create_task(self, task_id: str, status: str = "queued") -> TaskRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_tasks (
                    id, status, run_id, error, cancel_requested, created_at, updated_at
                )
                VALUES (?, ?, NULL, NULL, 0, datetime('now'), datetime('now'))
                """,
                (task_id, status),
            )
        return self.get_task(task_id)

    def update_task(
        self,
        task_id: str,
        status: str,
        run_id: str | None = None,
        error: str | None = None,
    ) -> TaskRecord:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE api_tasks
                SET status = ?,
                    run_id = COALESCE(?, run_id),
                    error = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (status, run_id, error, task_id),
            )
        return self.get_task(task_id)

    def request_task_cancel(self, task_id: str) -> TaskRecord:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE api_tasks
                SET cancel_requested = 1,
                    status = CASE
                        WHEN status IN ('completed', 'failed', 'cancelled') THEN status
                        ELSE 'cancel_requested'
                    END,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (task_id,),
            )
        return self.get_task(task_id)

    def task_cancel_requested(self, task_id: str) -> bool:
        return self.get_task(task_id).cancel_requested

    def get_task(self, task_id: str) -> TaskRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM api_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"Task '{task_id}' not found")
        data = dict(row)
        data["cancel_requested"] = bool(data["cancel_requested"])
        return TaskRecord.model_validate(data)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    run_mode TEXT NOT NULL DEFAULT 'optimize',
                    status TEXT NOT NULL,
                    stop_reason TEXT,
                    best_score REAL,
                    best_version INTEGER,
                    total_cost_usd REAL NOT NULL,
                    iterations_count INTEGER NOT NULL,
                    target_model TEXT NOT NULL,
                    reasoning_model TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS iterations (
                    run_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    score REAL NOT NULL,
                    pass_rate REAL NOT NULL,
                    total_cost_usd REAL NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, version),
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS verdicts (
                    run_id TEXT NOT NULL,
                    iteration_version INTEGER NOT NULL,
                    test_case_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    tokens_in INTEGER NOT NULL,
                    tokens_out INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    tags TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY (run_id, iteration_version)
                        REFERENCES iterations(run_id, version)
                );

                CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
                CREATE INDEX IF NOT EXISTS idx_verdicts_run ON verdicts(run_id);
                CREATE INDEX IF NOT EXISTS idx_verdicts_case ON verdicts(test_case_id);

                CREATE TABLE IF NOT EXISTS api_tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    run_id TEXT,
                    error TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_api_tasks_updated ON api_tasks(updated_at);
                """
            )
            existing_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "run_mode" not in existing_columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN run_mode TEXT NOT NULL DEFAULT 'optimize'"
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class CompositeRunStore:
    def __init__(self, *stores):
        self.stores = stores

    async def save_run(self, run: OptimizationRun) -> None:
        for store in self.stores:
            await store.save_run(run)

    async def save_iteration(self, run: OptimizationRun) -> None:
        for store in self.stores:
            await store.save_iteration(run)

    async def load_run(self, run_id: str) -> OptimizationRun:
        return await self.stores[0].load_run(run_id)


def _summary(run: OptimizationRun) -> RunSummary:
    best = run.best_iteration
    return RunSummary(
        id=run.id,
        run_mode=run.run_mode,
        status=run.status,
        stop_reason=run.stop_reason,
        best_score=best.score if best else None,
        best_version=best.version if best else None,
        total_cost_usd=run.total_cost_usd,
        iterations_count=len(run.iterations),
        target_model=f"{run.config.target_model.provider}/{run.config.target_model.model_id}",
        reasoning_model=f"{run.config.reasoning_model.provider}/{run.config.reasoning_model.model_id}",
        started_at=run.started_at.isoformat(),
        ended_at=run.ended_at.isoformat() if run.ended_at else None,
    )
