from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .backpack import counters_for, discover, is_active, read_snapshot, systemctl
from .db import Database

log = logging.getLogger("backpack-manager")


def bytes_from_amount(amount: float, unit: str) -> int:
    factors = {
        "GB": 1000**3,
        "TB": 1000**4,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }
    if unit not in factors:
        raise ValueError("unsupported unit")
    if amount < 0:
        raise ValueError("amount must be non-negative")
    return int(amount * factors[unit])


class TunnelManager:
    def __init__(self, db: Database, config_dir: str = "/etc/backpack"):
        self.db = db
        self.config_dir = config_dir
        self._stop = threading.Event()

    def scan(self) -> int:
        items = discover(self.config_dir)
        self.db.sync_discovery(items)
        return len(items)

    def _snapshot_for_row(self, row: dict[str, Any]):
        return read_snapshot(Path(row["metrics_path"]))

    def current_counters(self, row: dict[str, Any]) -> tuple[Optional[int], Optional[int], Optional[str]]:
        snap = self._snapshot_for_row(row)
        if not snap:
            return None, None, "metrics unavailable"
        # Prefer role written by the running BackPack engine.
        if snap.role and snap.role != "unknown" and snap.role != row.get("role"):
            row = dict(row)
            row["role"] = snap.role
        try:
            download, upload = counters_for(snap, row.get("direction") or "auto")
        except ValueError as exc:
            return None, None, str(exc)
        return download, upload, None

    def poll_one(self, row: dict[str, Any]) -> dict[str, Any]:
        download, upload, counter_error = self.current_counters(row)
        usage = int(row.get("usage_bytes") or 0)
        if download is not None:
            usage = self.db.update_counter(row["name"], download)
            row = self.db.get(row["name"]) or row

        reason = None
        now = int(time.time())
        if int(row.get("manual_suspended") or 0):
            reason = "manual"
        elif int(row.get("managed") or 0):
            quota = row.get("quota_bytes")
            expires = row.get("expires_at")
            if quota is not None and int(quota) > 0 and usage >= int(quota):
                reason = "quota"
            elif expires is not None and int(expires) > 0 and now >= int(expires):
                reason = "expired"

        if reason:
            # Enforce continuously: if someone starts an exhausted/expired
            # tunnel outside this manager, stop it again on the next poll.
            if row.get("suspended_reason") != reason or is_active(row["name"]):
                ok, out = systemctl("stop", row["name"])
                if ok or not is_active(row["name"]):
                    if row.get("suspended_reason") != reason:
                        self.db.set_suspended(row["name"], reason, manual=(reason == "manual"))
                else:
                    log.error("failed to stop %s: %s", row["name"], out)
        elif row.get("suspended_reason") in {"quota", "expired"} and is_active(row["name"]):
            # A limit was extended and the operator restarted the service.
            self.db.set_suspended(row["name"], None, manual=False)
        return {
            "download_counter": download,
            "upload_counter": upload,
            "counter_error": counter_error,
            "usage_bytes": usage,
            "reason": reason,
        }

    def poll(self) -> None:
        self.scan()
        for row in self.db.list():
            if not int(row.get("present") or 0):
                continue
            try:
                self.poll_one(row)
            except Exception:
                log.exception("poll failed for tunnel %s", row.get("name"))

    def run(self, interval: int = 15) -> None:
        interval = max(5, int(interval))
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.poll()
            except Exception:
                log.exception("manager poll failed")
            elapsed = time.monotonic() - started
            self._stop.wait(max(1, interval - elapsed))

    def stop(self) -> None:
        self._stop.set()

    def set_limits(
        self,
        name: str,
        quota_bytes: Optional[int],
        expires_at: Optional[int],
        direction: str = "auto",
        reset_usage: bool = True,
    ) -> None:
        row = self.db.get(name)
        if not row:
            raise KeyError(name)
        temp = dict(row)
        temp["direction"] = direction
        download, _, err = self.current_counters(temp)
        if direction == "auto" and err and reset_usage and "cannot infer" in err:
            raise ValueError(err)
        self.db.set_limits(name, quota_bytes, expires_at, direction, reset_usage, download)

    def reset_usage(self, name: str) -> None:
        row = self.db.get(name)
        if not row:
            raise KeyError(name)
        download, _, err = self.current_counters(row)
        if err:
            raise ValueError(err)
        self.db.reset_usage(name, download)

    def suspend(self, name: str) -> None:
        row = self.db.get(name)
        if not row:
            raise KeyError(name)
        ok, out = systemctl("stop", name)
        if not ok and is_active(name):
            raise RuntimeError(out or "failed to stop tunnel")
        self.db.set_suspended(name, "manual", manual=True)

    def resume(self, name: str) -> None:
        row = self.db.get(name)
        if not row:
            raise KeyError(name)
        now = int(time.time())
        quota = row.get("quota_bytes")
        if quota is not None and int(quota) > 0 and int(row.get("usage_bytes") or 0) >= int(quota):
            raise ValueError("download quota is exhausted; increase or reset it first")
        expires = row.get("expires_at")
        if expires is not None and int(expires) > 0 and now >= int(expires):
            raise ValueError("tunnel is expired; extend it first")
        ok, out = systemctl("start", name)
        if not ok:
            raise RuntimeError(out or "failed to start tunnel")
        self.db.set_suspended(name, None, manual=False)

    def api_rows(self) -> list[dict[str, Any]]:
        out = []
        for row in self.db.list():
            item = dict(row)
            try:
                item["ports"] = json.loads(item.pop("ports_json") or "[]")
            except json.JSONDecodeError:
                item["ports"] = []
            download, upload, err = self.current_counters(item)
            item["download_counter"] = download
            item["upload_counter"] = upload
            item["counter_error"] = err
            item["active"] = is_active(item["name"]) if int(item.get("present") or 0) else False
            out.append(item)
        return out
