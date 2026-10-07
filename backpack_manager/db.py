from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS tunnels (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'unknown',
    transport TEXT NOT NULL DEFAULT '',
    ports_json TEXT NOT NULL DEFAULT '[]',
    config_path TEXT NOT NULL DEFAULT '',
    metrics_path TEXT NOT NULL DEFAULT '',
    present INTEGER NOT NULL DEFAULT 1,
    discovered_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    managed INTEGER NOT NULL DEFAULT 0,
    quota_bytes INTEGER,
    expires_at INTEGER,
    direction TEXT NOT NULL DEFAULT 'auto',
    usage_bytes INTEGER NOT NULL DEFAULT 0,
    last_download_counter INTEGER,
    suspended_reason TEXT,
    manual_suspended INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tunnel_name TEXT NOT NULL,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_tunnel_ts ON events(tunnel_name, ts DESC);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def event(self, name: str, kind: str, detail: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events(tunnel_name,ts,kind,detail) VALUES(?,?,?,?)",
                (name, int(time.time()), kind, detail[:1000]),
            )

    def sync_discovery(self, items: Iterable[Any]) -> None:
        now = int(time.time())
        names = set()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    names.add(item.name)
                    conn.execute(
                        """
                        INSERT INTO tunnels(name,role,transport,ports_json,config_path,metrics_path,present,discovered_at,last_seen_at,updated_at)
                        VALUES(?,?,?,?,?,?,1,?,?,?)
                        ON CONFLICT(name) DO UPDATE SET
                          role=excluded.role,
                          transport=excluded.transport,
                          ports_json=excluded.ports_json,
                          config_path=excluded.config_path,
                          metrics_path=excluded.metrics_path,
                          present=1,
                          last_seen_at=excluded.last_seen_at,
                          updated_at=excluded.updated_at
                        """,
                        (
                            item.name,
                            item.role,
                            item.transport,
                            json.dumps(item.ports, ensure_ascii=False),
                            item.config_path,
                            item.metrics_path,
                            now,
                            now,
                            now,
                        ),
                    )
                if names:
                    placeholders = ",".join("?" for _ in names)
                    conn.execute(
                        f"UPDATE tunnels SET present=0, updated_at=? WHERE name NOT IN ({placeholders})",
                        (now, *sorted(names)),
                    )
                else:
                    conn.execute("UPDATE tunnels SET present=0, updated_at=?", (now,))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get(self, name: str) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tunnels WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM tunnels ORDER BY present DESC, name COLLATE NOCASE").fetchall()
        return [dict(r) for r in rows]

    def update_counter(self, name: str, current: int) -> int:
        """Accumulate only the delta of one tunnel-level download counter.

        One BackPack metrics file represents the entire tunnel, so all forwarded
        ports are already aggregated before this method sees the counter.
        """
        current = max(0, int(current))
        now = int(time.time())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT usage_bytes,last_download_counter FROM tunnels WHERE name=?",
                    (name,),
                ).fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    return 0
                usage = int(row["usage_bytes"] or 0)
                last = row["last_download_counter"]
                if last is None:
                    delta = 0
                elif current >= int(last):
                    delta = current - int(last)
                else:
                    # BackPack normally persists counters across restarts, but
                    # if the metrics file was reset/recreated, count forward
                    # from zero instead of subtracting or losing prior usage.
                    delta = current
                usage += delta
                conn.execute(
                    "UPDATE tunnels SET usage_bytes=?,last_download_counter=?,updated_at=? WHERE name=?",
                    (usage, current, now, name),
                )
                conn.execute("COMMIT")
                return usage
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def set_limits(
        self,
        name: str,
        quota_bytes: Optional[int],
        expires_at: Optional[int],
        direction: str,
        reset_usage: bool,
        current_counter: Optional[int],
    ) -> None:
        if direction not in {"auto", "in", "out"}:
            raise ValueError("direction must be auto, in or out")
        now = int(time.time())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if reset_usage:
                    conn.execute(
                        """UPDATE tunnels SET managed=1,quota_bytes=?,expires_at=?,direction=?,usage_bytes=0,
                           last_download_counter=?,suspended_reason=NULL,manual_suspended=0,updated_at=? WHERE name=?""",
                        (quota_bytes, expires_at, direction, current_counter, now, name),
                    )
                else:
                    conn.execute(
                        """UPDATE tunnels SET managed=1,quota_bytes=?,expires_at=?,direction=?,updated_at=? WHERE name=?""",
                        (quota_bytes, expires_at, direction, now, name),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.event(name, "limits_updated", f"quota={quota_bytes}, expires={expires_at}, direction={direction}, reset={reset_usage}")

    def add_quota(self, name: str, amount_bytes: int) -> None:
        amount_bytes = max(0, int(amount_bytes))
        with self.connect() as conn:
            conn.execute(
                "UPDATE tunnels SET quota_bytes=COALESCE(quota_bytes,0)+?,managed=1,updated_at=? WHERE name=?",
                (amount_bytes, int(time.time()), name),
            )
        self.event(name, "quota_added", str(amount_bytes))

    def reset_usage(self, name: str, current_counter: Optional[int]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE tunnels SET usage_bytes=0,last_download_counter=?,suspended_reason=NULL,updated_at=? WHERE name=?",
                (current_counter, int(time.time()), name),
            )
        self.event(name, "usage_reset")

    def set_suspended(self, name: str, reason: Optional[str], manual: bool = False) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE tunnels SET suspended_reason=?,manual_suspended=?,updated_at=? WHERE name=?",
                (reason, 1 if manual else 0, int(time.time()), name),
            )
        self.event(name, "suspended" if reason else "resumed", reason or "")

    def set_expiry(self, name: str, expires_at: Optional[int]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE tunnels SET expires_at=?,managed=1,updated_at=? WHERE name=?",
                (expires_at, int(time.time()), name),
            )
        self.event(name, "expiry_updated", str(expires_at))

    def recent_events(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT ts,kind,detail FROM events WHERE tunnel_name=? ORDER BY id DESC LIMIT ?",
                (name, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(r) for r in rows]
