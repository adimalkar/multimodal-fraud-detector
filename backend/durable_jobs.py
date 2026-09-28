"""Persistent, tenant-scoped queue for the opt-in durable backend path."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA_VERSION = "screening-v1"


class QueueUnavailable(RuntimeError):
    pass


class QuotaExceeded(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


class JobBusy(RuntimeError):
    pass


class DurableJobStore:
    def __init__(self, database_url: str | None = None, sqlite_path: str | None = None):
        self.database_url = database_url or None
        self.sqlite_path = sqlite_path or os.getenv("DURABLE_SQLITE_PATH", "database/durable_jobs.db")
        self.postgres = bool(self.database_url)
        if self.postgres and not self.database_url.startswith(("postgresql://", "postgres://")):
            raise QueueUnavailable("DURABLE_DATABASE_URL must be a PostgreSQL URL")

    def _connect(self):
        if self.postgres:
            import psycopg2
            import psycopg2.extras

            # Never fall back to ephemeral SQLite when production PostgreSQL is unavailable.
            return psycopg2.connect(
                self.database_url, cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=5,
            )
        path = Path(self.sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, conn, query: str, params=()):
        cursor = conn.cursor()
        cursor.execute(query.replace("?", "%s") if self.postgres else query, params)
        return cursor

    def initialize(self):
        conn = self._connect()
        try:
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS durable_schema_version (
                    component TEXT PRIMARY KEY, version INTEGER NOT NULL
                )
            """)
            self._execute(conn, """
                INSERT INTO durable_schema_version(component, version)
                VALUES ('jobs', 1) ON CONFLICT DO NOTHING
            """)
            version = self._row(self._execute(
                conn, "SELECT version FROM durable_schema_version WHERE component='jobs'"
            ))
            if version["version"] != 1:
                raise QueueUnavailable("Unsupported durable job schema version")
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS durable_jobs (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    parent_id TEXT,
                    item_index INTEGER,
                    status TEXT NOT NULL,
                    filename TEXT,
                    media_type TEXT,
                    content_type TEXT,
                    artifact_key TEXT,
                    artifact_sha256 TEXT,
                    idempotency_key TEXT,
                    request_fingerprint TEXT,
                    pipeline_version TEXT NOT NULL,
                    reserved_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
                    actual_cost_usd DOUBLE PRECISION,
                    result_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    stage TEXT,
                    progress INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    billing_started INTEGER NOT NULL DEFAULT 0,
                    lease_token TEXT,
                    lease_until DOUBLE PRECISION,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                )
            """)
            self._execute(conn, """
                CREATE UNIQUE INDEX IF NOT EXISTS durable_jobs_idempotency
                ON durable_jobs(owner_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL AND parent_id IS NULL
            """)
            self._execute(conn, """
                CREATE INDEX IF NOT EXISTS durable_jobs_queue
                ON durable_jobs(status, created_at)
            """)
            self._execute(conn, """
                CREATE INDEX IF NOT EXISTS durable_jobs_parent
                ON durable_jobs(parent_id, item_index)
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS durable_usage (
                    job_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    reserved_cost_usd DOUBLE PRECISION NOT NULL,
                    actual_cost_usd DOUBLE PRECISION
                )
            """)
            self._execute(conn, """
                CREATE INDEX IF NOT EXISTS durable_usage_owner_time
                ON durable_usage(owner_id, created_at)
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS durable_workers (
                    worker_id TEXT PRIMARY KEY, updated_at DOUBLE PRECISION NOT NULL
                )
            """)
            self._execute(conn, """
                INSERT INTO durable_usage(
                    job_id, owner_id, created_at, reserved_cost_usd, actual_cost_usd
                )
                SELECT id, owner_id, created_at, reserved_cost_usd, actual_cost_usd
                FROM durable_jobs WHERE kind='item' ON CONFLICT DO NOTHING
            """)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row(cursor):
        row = cursor.fetchone()
        return dict(row) if row else None

    def get(self, job_id: str, owner_id: str):
        conn = self._connect()
        try:
            return self._row(self._execute(
                conn, "SELECT * FROM durable_jobs WHERE id=? AND owner_id=?", (job_id, owner_id)
            ))
        finally:
            conn.close()

    def get_by_idempotency(self, owner_id: str, key: str):
        conn = self._connect()
        try:
            return self._row(self._execute(
                conn,
                "SELECT * FROM durable_jobs WHERE owner_id=? AND idempotency_key=? AND parent_id IS NULL",
                (owner_id, key),
            ))
        finally:
            conn.close()

    def children(self, parent_id: str, owner_id: str):
        conn = self._connect()
        try:
            return [dict(row) for row in self._execute(
                conn,
                "SELECT * FROM durable_jobs WHERE parent_id=? AND owner_id=? ORDER BY item_index",
                (parent_id, owner_id),
            ).fetchall()]
        finally:
            conn.close()

    def create(
        self, owner_id: str, items: list[dict], *, idempotency_key: str | None,
        request_fingerprint: str, max_daily_jobs: int, max_daily_reserved_usd: float,
        reserve_per_job_usd: float,
    ) -> tuple[dict, bool]:
        """Atomically check tenant quota and enqueue one item or a batch."""
        if (
            not items or max_daily_jobs < 1
            or not math.isfinite(max_daily_reserved_usd) or max_daily_reserved_usd <= 0
            or not math.isfinite(reserve_per_job_usd) or reserve_per_job_usd <= 0
        ):
            raise ValueError("Invalid queue or quota configuration")
        now = time.time()
        conn = self._connect()
        try:
            if self.postgres:
                self._execute(conn, "SELECT pg_advisory_xact_lock(hashtext(?))", (owner_id,))
            else:
                self._execute(conn, "BEGIN IMMEDIATE")
            if idempotency_key:
                existing = self._row(self._execute(
                    conn,
                    "SELECT * FROM durable_jobs WHERE owner_id=? AND idempotency_key=? AND parent_id IS NULL",
                    (owner_id, idempotency_key),
                ))
                if existing:
                    if existing["request_fingerprint"] != request_fingerprint:
                        raise IdempotencyConflict("Idempotency key was used for different evidence")
                    conn.commit()
                    return existing, False
            since = now - 86400
            usage = self._row(self._execute(conn, """
                SELECT COUNT(*) AS jobs,
                       COALESCE(SUM(COALESCE(actual_cost_usd, reserved_cost_usd)), 0) AS cost
                FROM durable_usage
                WHERE owner_id=? AND created_at>=?
            """, (owner_id, since)))
            if usage["jobs"] + len(items) > max_daily_jobs:
                raise QuotaExceeded("Daily analysis count limit reached")
            if float(usage["cost"]) + len(items) * reserve_per_job_usd > max_daily_reserved_usd:
                raise QuotaExceeded("Daily analysis budget limit reached")
            parent_id = str(uuid.uuid4()) if len(items) > 1 else None
            if parent_id:
                self._insert(
                    conn, parent_id, owner_id, "batch", None, None, "queued", None,
                    idempotency_key, request_fingerprint, 0, now,
                )
            for index, item in enumerate(items):
                job_id = str(uuid.uuid4())
                self._insert(
                    conn, job_id, owner_id, "item", parent_id, index if parent_id else None,
                    "queued", item, idempotency_key if not parent_id else None,
                    request_fingerprint if not parent_id else None, reserve_per_job_usd, now,
                )
                self._execute(conn, """
                    INSERT INTO durable_usage(
                        job_id, owner_id, created_at, reserved_cost_usd
                    ) VALUES (?,?,?,?)
                """, (job_id, owner_id, now, reserve_per_job_usd))
            primary_id = parent_id or job_id
            primary = self._row(self._execute(
                conn, "SELECT * FROM durable_jobs WHERE id=?", (primary_id,)
            ))
            conn.commit()
            return primary, True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _insert(
        self, conn, job_id, owner_id, kind, parent_id, item_index, status, item,
        idempotency_key, request_fingerprint, reserved_cost, now,
    ):
        self._execute(conn, """
            INSERT INTO durable_jobs (
                id, owner_id, kind, parent_id, item_index, status,
                filename, media_type, content_type, artifact_key, artifact_sha256,
                idempotency_key, request_fingerprint, pipeline_version,
                reserved_cost_usd, stage, progress, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            job_id, owner_id, kind, parent_id, item_index, status,
            item.get("filename") if item else None,
            item.get("media_type") if item else None,
            item.get("content_type") if item else None,
            item.get("artifact_key") if item else None,
            item.get("artifact_sha256") if item else None,
            idempotency_key, request_fingerprint, SCHEMA_VERSION,
            reserved_cost, "Queued for screening", 0, now, now,
        ))

    def claim(self, lease_seconds: int = 900):
        """Claim one queued item. Expired paid work is never re-billed automatically."""
        now = time.time()
        conn = self._connect()
        try:
            if self.postgres:
                row = self._row(self._execute(conn, """
                    SELECT * FROM durable_jobs WHERE kind='item' AND status='queued'
                    ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
                """))
            else:
                self._execute(conn, "BEGIN IMMEDIATE")
                row = self._row(self._execute(conn, """
                    SELECT * FROM durable_jobs WHERE kind='item' AND status='queued'
                    ORDER BY created_at, id LIMIT 1
                """))
            if not row:
                conn.commit()
                return None
            token = str(uuid.uuid4())
            self._execute(conn, """
                UPDATE durable_jobs SET status='processing', attempts=attempts+1,
                    lease_token=?, lease_until=?, stage='Preparing evidence', progress=20,
                    updated_at=? WHERE id=?
            """, (token, now + lease_seconds, now, row["id"]))
            conn.commit()
            row.update(
                status="processing", lease_token=token, lease_until=now + lease_seconds,
                attempts=row["attempts"] + 1,
            )
            return row
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_billing_started(self, job_id: str, token: str):
        self._transition(job_id, token, """
            UPDATE durable_jobs SET billing_started=1, stage='Visual screening in progress',
                progress=50, updated_at=? WHERE id=? AND lease_token=? AND status='processing'
        """)

    def heartbeat(self, job_id: str, token: str, lease_seconds: int = 900) -> bool:
        conn = self._connect()
        try:
            now = time.time()
            cursor = self._execute(conn, """
                UPDATE durable_jobs SET lease_until=?, updated_at=?
                WHERE id=? AND lease_token=? AND status='processing'
            """, (now + lease_seconds, now, job_id, token))
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()

    def _transition(self, job_id, token, query, params=()):
        conn = self._connect()
        try:
            cursor = self._execute(conn, query, (*params, time.time(), job_id, token))
            if cursor.rowcount != 1:
                raise QueueUnavailable("Job lease was lost")
            conn.commit()
        finally:
            conn.close()

    def complete(self, job_id: str, token: str, result: dict):
        usage = result.get("model_usage") or {}
        cost = usage.get("cost")
        if (
            not isinstance(cost, (int, float)) or isinstance(cost, bool)
            or not math.isfinite(cost) or cost < 0
        ):
            cost = None
        conn = self._connect()
        try:
            cursor = self._execute(conn, """
                UPDATE durable_jobs SET status='completed', result_json=?, actual_cost_usd=?,
                    stage='Analysis complete', progress=100, lease_token=NULL, lease_until=NULL,
                    updated_at=? WHERE id=? AND lease_token=? AND status='processing'
            """, (json.dumps(result), cost, time.time(), job_id, token))
            if cursor.rowcount != 1:
                raise QueueUnavailable("Job lease was lost")
            if cost is not None:
                self._execute(conn, """
                    UPDATE durable_usage SET actual_cost_usd=? WHERE job_id=?
                """, (cost, job_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def fail(self, job_id: str, token: str, code: str, message: str, *, retry: bool = False):
        status = "queued" if retry else "failed"
        self._transition(job_id, token, """
            UPDATE durable_jobs SET status=?, error_code=?, error_message=?,
                stage=?, progress=?, lease_token=NULL, lease_until=NULL,
                updated_at=? WHERE id=? AND lease_token=? AND status='processing'
        """, (
            status, code, message[:500], "Retry queued" if retry else "Analysis failed",
            0 if retry else 100,
        ))

    def recover_expired(self):
        now = time.time()
        conn = self._connect()
        try:
            cursor = self._execute(conn, """
                UPDATE durable_jobs SET status='failed',
                    error_code='WORKER_INTERRUPTED_REVIEW_REQUIRED',
                    error_message='Worker stopped before confirming completion; review before retrying.',
                    stage='Analysis interrupted', progress=100,
                    lease_token=NULL, lease_until=NULL, updated_at=?
                WHERE kind='item' AND status='processing' AND lease_until<?
            """, (now, now))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def active_counts(self):
        conn = self._connect()
        try:
            row = self._row(self._execute(conn, """
                SELECT COUNT(*) AS active_items,
                       COUNT(DISTINCT parent_id) AS active_batches
                FROM durable_jobs
                WHERE kind='item' AND status IN ('queued','processing')
            """))
            return {
                "active_jobs": row["active_items"],
                "active_batches": row["active_batches"],
            }
        finally:
            conn.close()

    def touch_worker(self, worker_id: str):
        conn = self._connect()
        try:
            self._execute(conn, """
                INSERT INTO durable_workers(worker_id, updated_at) VALUES (?,?)
                ON CONFLICT(worker_id) DO UPDATE SET updated_at=excluded.updated_at
            """, (worker_id, time.time()))
            conn.commit()
        finally:
            conn.close()

    def worker_recent(self, seconds: int = 150) -> bool:
        conn = self._connect()
        try:
            row = self._row(self._execute(
                conn, "SELECT MAX(updated_at) AS last_seen FROM durable_workers"
            ))
            return bool(row and row["last_seen"] and time.time() - row["last_seen"] <= seconds)
        finally:
            conn.close()

    def begin_delete(self, job_id: str, owner_id: str, kind: str) -> list[dict] | None:
        """Mark a terminal or queued root and its children for private artifact deletion."""
        conn = self._connect()
        try:
            if not self.postgres:
                self._execute(conn, "BEGIN IMMEDIATE")
            suffix = " FOR UPDATE" if self.postgres else ""
            root = self._row(self._execute(
                conn,
                "SELECT * FROM durable_jobs WHERE id=? AND owner_id=? AND kind=? AND parent_id IS NULL" + suffix,
                (job_id, owner_id, kind),
            ))
            if not root:
                conn.commit()
                return None
            children = [dict(row) for row in self._execute(
                conn, "SELECT * FROM durable_jobs WHERE parent_id=? ORDER BY item_index" + suffix,
                (job_id,),
            ).fetchall()]
            rows = [root, *children]
            if any(row["status"] == "processing" for row in rows):
                raise JobBusy("Analysis is processing; retry deletion after it finishes")
            for row in rows:
                self._execute(conn, """
                    UPDATE durable_jobs SET status='deleting', stage='Deleting evidence',
                        updated_at=? WHERE id=?
                """, (time.time(), row["id"]))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def finalize_delete(self, job_id: str, owner_id: str):
        conn = self._connect()
        try:
            self._execute(conn, """
                DELETE FROM durable_jobs WHERE owner_id=? AND (id=? OR parent_id=?)
                AND status='deleting'
            """, (owner_id, job_id, job_id))
            conn.commit()
        finally:
            conn.close()

    def expired_roots(self, retention_seconds: int, limit: int = 20) -> list[dict]:
        conn = self._connect()
        try:
            return [dict(row) for row in self._execute(conn, """
                SELECT id, owner_id, kind FROM durable_jobs
                WHERE parent_id IS NULL AND (
                    status='deleting' OR (created_at<? AND status!='processing')
                )
                ORDER BY CASE WHEN status='deleting' THEN 0 ELSE 1 END, created_at
                LIMIT ?
            """, (time.time() - retention_seconds, limit)).fetchall()]
        finally:
            conn.close()

    def prune_usage(self, retention_seconds: int) -> int:
        if retention_seconds <= 86400:
            raise ValueError("Usage retention must exceed the daily quota window")
        conn = self._connect()
        try:
            cursor = self._execute(
                conn, "DELETE FROM durable_usage WHERE created_at<?",
                (time.time() - retention_seconds,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
