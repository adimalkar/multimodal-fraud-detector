"""Regression tests for database dialect handling, transaction safety, and connection cleanup."""

from contextlib import contextmanager

import pytest

from backend import db_service


class _FakePostgresCursor:
    def __init__(self, conn, queries):
        self._conn = conn
        self._queries = queries
        self._last_query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        if self._conn.aborted:
            raise RuntimeError("current transaction is aborted")
        if "is_processed = 1" in query:
            self._conn.aborted = True
            raise RuntimeError("operator does not exist: boolean = integer")
        if self._conn.fail_on and self._conn.fail_on in query:
            self._conn.aborted = True
            raise RuntimeError("simulated DDL/query failure")
        self._last_query = query
        self._queries.append((query, params))

    def fetchone(self):
        if "SELECT COUNT(*)" in self._last_query:
            return [2]
        if "SELECT AVG(" in self._last_query:
            return [0.75]
        return [1]

    def fetchall(self):
        if "ORDER BY id DESC" in self._last_query:
            return [{
                "id": 1,
                "filename": "claim.jpg",
                "media_type": "Image",
                "fraud_category": "General Claim",
                "ground_truth": "Pending Review",
                "ai_prediction": "Fake",
                "confidence": 0.9,
                "risk_score": 0.85,
                "severity_tier": "HIGH_RISK",
                "recommended_action": "MANUAL_REVIEW",
                "vision_findings": "Edited edges",
                "final_reasoning": "Suspicious edit",
                "processing_time": 1.2,
                "processed_at": "2026-11-25 00:00:00",
            }]
        return []


class _FakePostgresConnection:
    cursor_factory = object()

    def __init__(self, fail_on=None):
        self.queries = []
        self.fail_on = fail_on
        self.aborted = False
        self.closed = False
        self.rollbacks = 0
        self.commits = 0

    def cursor(self):
        return _FakePostgresCursor(self, self.queries)

    def commit(self):
        if self.aborted:
            raise RuntimeError("cannot commit aborted transaction")
        self.commits += 1

    def rollback(self):
        self.aborted = False
        self.rollbacks += 1

    def close(self):
        self.closed = True


@contextmanager
def _sqlite_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "DATABASE_URL", None)
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "test.db"))
    yield


def test_postgres_queries_avoid_boolean_integer_comparison_and_close_connection(monkeypatch):
    monkeypatch.setattr(db_service, "DATABASE_URL", "postgresql://user:pass@localhost:5432/fraud")
    conns = []

    def fake_get_connection():
        conn = _FakePostgresConnection()
        conns.append(conn)
        return conn

    monkeypatch.setattr(db_service, "get_connection", fake_get_connection)

    summary = db_service.get_analytics_summary()
    assert summary["database_engine"] == "PostgreSQL"
    assert summary["processed_records"] == 2
    assert conns[0].closed is True
    assert all("is_processed = 1" not in sql for sql, _ in conns[0].queries)

    csv_text = db_service.export_evaluations_csv()
    assert "claim.jpg" in csv_text
    assert conns[1].closed is True
    assert all("is_processed = 1" not in sql for sql, _ in conns[1].queries)


def test_ensure_columns_rolls_back_aborted_postgres_transaction(monkeypatch):
    monkeypatch.setattr(db_service, "DATABASE_URL", "postgresql://user:pass@localhost:5432/fraud")
    conn = _FakePostgresConnection(fail_on="ALTER TABLE evidence ADD COLUMN IF NOT EXISTS risk_score")

    db_service.ensure_columns(conn)

    assert conn.rollbacks >= 1
    assert conn.aborted is False
    assert any("CREATE UNIQUE INDEX IF NOT EXISTS evidence_job_id_unique" in sql for sql, _ in conn.queries)


def test_get_connection_closes_partial_postgres_conn_before_sqlite_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "DATABASE_URL", "postgresql://user:pass@localhost:5432/fraud")
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "fallback.db"))
    monkeypatch.delenv("DURABLE_JOBS_ENABLED", raising=False)

    created = []
    import psycopg2

    def fake_connect(*args, **kwargs):
        conn = _FakePostgresConnection(fail_on="CREATE TABLE IF NOT EXISTS evidence")
        created.append(conn)
        return conn

    monkeypatch.setattr(psycopg2, "connect", fake_connect)

    conn = db_service.get_connection()
    try:
        assert created[0].closed is True
        assert not db_service._is_postgres_conn(conn)
    finally:
        conn.close()

    # Analytics summary reports actual SQLite engine when falling back.
    summary = db_service.get_analytics_summary()
    assert summary["database_engine"] == "SQLite"


def test_db_operations_close_connection_on_query_failure(monkeypatch):
    monkeypatch.setattr(db_service, "DATABASE_URL", "postgresql://user:pass@localhost:5432/fraud")
    conns = []

    def make_conn(fail_on):
        conn = _FakePostgresConnection(fail_on=fail_on)
        conns.append(conn)
        return conn

    monkeypatch.setattr(db_service, "get_connection", lambda: make_conn("INSERT INTO evidence"))
    with pytest.raises(RuntimeError, match="simulated"):
        db_service.save_evaluation("a.jpg", "Image", "Fake", 0.9, "reason")
    assert conns[-1].closed is True

    monkeypatch.setattr(db_service, "get_connection", lambda: make_conn("SELECT COUNT(*) FROM evidence"))
    with pytest.raises(RuntimeError, match="simulated"):
        db_service.get_analytics_summary()
    assert conns[-1].closed is True

    monkeypatch.setattr(db_service, "get_connection", lambda: make_conn("LIMIT"))
    with pytest.raises(RuntimeError, match="simulated"):
        db_service.get_evaluations_list()
    assert conns[-1].closed is True

    monkeypatch.setattr(db_service, "get_connection", lambda: make_conn("ORDER BY id DESC"))
    with pytest.raises(RuntimeError, match="simulated"):
        db_service.export_evaluations_csv()
    assert conns[-1].closed is True


def test_get_evaluations_list_clamps_negative_pagination_bounds(monkeypatch, tmp_path):
    with _sqlite_db(monkeypatch, tmp_path):
        db_service.save_evaluation("first.jpg", "Image", "Real", 0.8, "ok")
        db_service.save_evaluation("second.jpg", "Image", "Fake", 0.9, "bad")

        assert db_service.get_evaluations_list(limit=-5, offset=-10) == []
        rows = db_service.get_evaluations_list(limit=10, offset=-3)
        assert [row["filename"] for row in rows] == ["second.jpg", "first.jpg"]
