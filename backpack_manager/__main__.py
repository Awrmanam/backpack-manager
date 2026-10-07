from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
from pathlib import Path

from .db import Database
from .manager import TunnelManager
from .web import AppServer, Handler


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["bind", "port", "database", "backpack_config_dir", "auth"]
    for key in required:
        if key not in cfg:
            raise SystemExit(f"missing config key: {key}")
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="Download-only quota manager for BackPack tunnels")
    ap.add_argument("--config", default="/etc/backpack-manager/config.json")
    args = ap.parse_args()
    cfg = load_config(args.config)

    logging.basicConfig(level=getattr(logging, str(cfg.get("log_level","INFO")).upper(), logging.INFO),format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = Database(cfg["database"])
    manager = TunnelManager(db, cfg["backpack_config_dir"])
    manager.poll()
    worker = threading.Thread(target=manager.run,args=(int(cfg.get("poll_interval_seconds",15)),),daemon=True,name="quota-worker")
    worker.start()

    server = AppServer((cfg["bind"], int(cfg["port"])), Handler, manager, cfg["auth"])
    def shutdown(*_):
        manager.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever(poll_interval=1)
    finally:
        manager.stop(); server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
