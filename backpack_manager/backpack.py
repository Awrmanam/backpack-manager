from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class Snapshot:
    name: str
    role: str
    transport: str
    bytes_in: int
    bytes_out: int
    connected: Optional[bool]
    taken: Optional[str]


@dataclass
class DiscoveredTunnel:
    name: str
    role: str
    transport: str
    ports: list[str]
    config_path: str
    metrics_path: str


def validate_name(name: str) -> str:
    if not SAFE_NAME_RE.fullmatch(name or ""):
        raise ValueError("invalid tunnel name")
    return name


def service_name(name: str) -> str:
    return f"backpack-{validate_name(name)}.service"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _section_body(text: str, section: str) -> str:
    pattern = re.compile(rf"(?ms)^\s*\[{re.escape(section)}\]\s*$\n(.*?)(?=^\s*\[|\Z)")
    m = pattern.search(text)
    return m.group(1) if m else ""


def _value(body: str, key: str) -> Optional[str]:
    m = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*(.+?)\s*$", body)
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.startswith(('"', "'")) and raw[-1:] == raw[:1]:
        return raw[1:-1]
    return raw


def _array_values(body: str, key: str) -> list[str]:
    m = re.search(rf"(?ms)^\s*{re.escape(key)}\s*=\s*\[(.*?)\]", body)
    if not m:
        return []
    raw = m.group(1)
    values = []
    for quoted, bare in re.findall(r'''["']([^"']+)["']|([^,\s]+)''', raw):
        v = (quoted or bare).strip()
        if v:
            values.append(v)
    return values


def parse_toml_summary(path: Path) -> tuple[str, str, list[str]]:
    """Parse only the BackPack fields we need without third-party TOML deps.

    BackPack's tunnel role is determined by which engine table exists. This
    intentionally avoids parsing secrets/tokens or rewriting the config.
    """
    text = _read_text(path)
    server = _section_body(text, "server")
    client = _section_body(text, "client")
    direct = _section_body(text, "direct")
    l3 = _section_body(text, "l3")

    if server and _value(server, "bind_addr") is not None:
        return "server", _value(server, "transport") or "", _array_values(server, "ports")
    if client and _value(client, "remote_addr") is not None:
        return "client", _value(client, "transport") or "", []
    if direct:
        role = _value(direct, "role") or "direct"
        transport = _value(direct, "transport") or "tcp"
        return role, f"direct/{transport}", _array_values(direct, "ports")
    if l3:
        role = _value(l3, "mode") or "l3"
        carrier = _value(l3, "carrier") or "udp"
        return role, f"l3/{carrier}", _array_values(l3, "ports")
    return "unknown", "", []


def read_snapshot(path: Path) -> Optional[Snapshot]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return Snapshot(
        name=str(data.get("name") or path.name[:-13] if path.name.endswith(".metrics.json") else path.stem),
        role=str(data.get("role") or "unknown"),
        transport=str(data.get("transport") or ""),
        bytes_in=max(0, int(data.get("bytes_in") or 0)),
        bytes_out=max(0, int(data.get("bytes_out") or 0)),
        connected=data.get("connected") if isinstance(data.get("connected"), bool) else None,
        taken=data.get("taken"),
    )


def discover(config_dir: str = "/etc/backpack") -> list[DiscoveredTunnel]:
    root = Path(config_dir)
    if not root.is_dir():
        return []
    tunnels: list[DiscoveredTunnel] = []
    for path in sorted(root.glob("*.toml")):
        name = path.stem
        if not SAFE_NAME_RE.fullmatch(name):
            continue
        try:
            role, transport, ports = parse_toml_summary(path)
        except OSError:
            continue
        metrics_path = root / f"{name}.metrics.json"
        snap = read_snapshot(metrics_path)
        if snap:
            if snap.role and snap.role != "unknown":
                role = snap.role
            if snap.transport:
                transport = snap.transport
        tunnels.append(
            DiscoveredTunnel(
                name=name,
                role=role,
                transport=transport,
                ports=ports,
                config_path=str(path),
                metrics_path=str(metrics_path),
            )
        )
    return tunnels


def auto_download_direction(role: str) -> Optional[str]:
    """Map tunnel-side counters to end-user download direction.

    On an Iran-side BackPack reverse *server*, response/download bytes arrive
    from the remote peer => bytes_in. On the remote *client*, the same response
    bytes leave toward the Iran peer => bytes_out.
    """
    r = (role or "").lower().strip()
    if r == "server" or r.endswith("server"):
        return "in"
    if r == "client" or r.endswith("client"):
        return "out"
    return None


def counters_for(snapshot: Snapshot, direction: str) -> tuple[int, int]:
    resolved = direction
    if direction == "auto":
        resolved = auto_download_direction(snapshot.role) or ""
    if resolved == "in":
        return snapshot.bytes_in, snapshot.bytes_out
    if resolved == "out":
        return snapshot.bytes_out, snapshot.bytes_in
    raise ValueError(f"cannot infer download direction for role {snapshot.role!r}")


def systemctl(action: str, name: str, timeout: int = 15) -> tuple[bool, str]:
    if action not in {"start", "stop", "restart", "is-active", "is-enabled"}:
        raise ValueError("unsupported systemctl action")
    unit = service_name(name)
    try:
        proc = subprocess.run(
            ["systemctl", action, unit],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return proc.returncode == 0, (proc.stdout or "").strip()


def is_active(name: str) -> bool:
    ok, out = systemctl("is-active", name)
    return ok and out.strip() == "active"
