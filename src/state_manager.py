import sqlite3
import json
import os
from datetime import datetime, timezone


class StateManager:
    def __init__(self, db_path: str = "data/state.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategy_status (
                name TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'INFO',
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT 'PASS',
                details TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_type TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_output TEXT,
                action TEXT,
                target TEXT,
                value REAL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                timestamp TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    def upsert_metric(self, key: str, value: float):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO metrics (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

    def get_metric(self, key: str) -> float | None:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM metrics WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else None

    def upsert_strategy(self, name: str, status: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO strategy_status (name, status, updated_at) VALUES (?, ?, ?)",
            (name, status, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

    def get_strategies(self) -> dict:
        conn = self._get_conn()
        rows = conn.execute("SELECT name, status FROM strategy_status").fetchall()
        conn.close()
        return {r["name"]: r["status"] for r in rows}

    def log_error(self, source: str, message: str, severity: str = "ERROR"):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO errors (source, message, severity, timestamp) VALUES (?, ?, ?, ?)",
            (source, message, severity, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

    def get_recent_errors(self, limit: int = 10) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT source, message, severity FROM errors ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def log_backtest(self, strategy: str, result: str, details: dict = None):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO backtest_results (strategy, result, details, timestamp) VALUES (?, ?, ?, ?)",
            (strategy, result, json.dumps(details or {}), datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

    def get_last_backtest(self) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT strategy, result, details FROM backtest_results ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return {"strategy": row["strategy"], "result": row["result"], "details": json.loads(row["details"])}
        return None

    def log_audit(self, audit_type: str, status: str, details: dict = None):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO audit_log (audit_type, status, details, timestamp) VALUES (?, ?, ?, ?)",
            (audit_type, status, json.dumps(details or {}), datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

    def get_avg_drawdown_7d(self) -> float:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT value FROM metrics WHERE key = ? AND updated_at >= datetime('now', '-7 days') ORDER BY updated_at",
            ("portfolio_drawdown",)
        ).fetchall()
        conn.close()
        if not rows:
            return 0.0
        total = sum(r["value"] for r in rows)
        return round(total / len(rows), 2)

    def log_decision(self, raw: str, action: str, target: str = None, value: float = None, status: str = "EXECUTED"):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO ai_decisions (raw_output, action, target, value, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (raw, action, target, value, status, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
