"""Append-only record of what each gateway request actually used.

Only figures the gateway measured itself are stored: provider-reported tokens,
measured latency, and the router's own cost estimate (labelled as an estimate).
No credential, prompt text, or invented quality score ever reaches this table.
"""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    route TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    cache_hit INTEGER NOT NULL,
    tokens_used INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    key_source TEXT
)
"""


class UsageLedger:
    def __init__(self, db_path: Optional[str] = None):
        # No I/O here: importing the gateway must not create files it never wrote to.
        self.db_path = str(db_path or settings.USAGE_DB_PATH)

    @contextmanager
    def _db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(_SCHEMA)
                yield conn
        finally:
            conn.close()

    def record(
        self,
        *,
        route: str,
        model: str,
        status: str,
        cache_hit: bool,
        tokens_used: int,
        latency_ms: float,
        estimated_cost_usd: float,
        key_source: Optional[str] = None,
    ) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT INTO usage_events (ts, route, model, status, cache_hit, tokens_used,"
                " latency_ms, estimated_cost_usd, key_source) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    time.time(), route, model, status, int(cache_hit), tokens_used,
                    latency_ms, estimated_cost_usd, key_source,
                ),
            )

    def totals(self) -> Dict[str, Any]:
        with self._db() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(tokens_used), 0), COALESCE(SUM(cache_hit), 0),"
                " COALESCE(AVG(latency_ms), 0), COALESCE(SUM(estimated_cost_usd), 0)"
                " FROM usage_events"
            ).fetchone()
        return {
            "requests": row[0],
            "tokens_used": row[1],
            "cache_hits": row[2],
            "avg_latency_ms": round(row[3], 2),
            "estimated_cost_usd": round(row[4], 6),
        }


    def per_route(self) -> Dict[str, Dict[str, Any]]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT route, COUNT(*), SUM(tokens_used), SUM(estimated_cost_usd)"
                " FROM usage_events GROUP BY route"
            ).fetchall()
        return {
            row[0]: {
                "requests": row[1],
                "tokens_used": row[2],
                "estimated_cost_usd": round(row[3], 6),
            }
            for row in rows
        }


usage_ledger = UsageLedger()
