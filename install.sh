#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo "Run as root: sudo ./install.sh" >&2; exit 1; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR=/opt/backpack-manager
ETC_DIR=/etc/backpack-manager
DATA_DIR=/var/lib/backpack-manager
CFG="$ETC_DIR/config.json"
UNIT=/etc/systemd/system/backpack-manager.service

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
python3 - <<'PY'
import sys
if sys.version_info < (3,8):
    raise SystemExit("Python 3.8+ is required")
PY
[[ -d /etc/backpack ]] || echo "Warning: /etc/backpack does not exist yet; tunnels will appear automatically when BackPack creates them."

install -d -m 0755 "$APP_DIR" "$ETC_DIR"
install -d -m 0700 "$DATA_DIR"
rm -rf "$APP_DIR/backpack_manager"
cp -a "$ROOT/backpack_manager" "$APP_DIR/"
chmod -R go-w "$APP_DIR"

if [[ ! -f "$CFG" ]]; then
  BPM_USER="${BPM_USER:-admin}"
  BPM_BIND="${BPM_BIND:-0.0.0.0}"
  BPM_PORT="${BPM_PORT:-8787}"
  BPM_PASSWORD="${BPM_PASSWORD:-$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)}"
  export BPM_USER BPM_BIND BPM_PORT BPM_PASSWORD CFG
  python3 - <<'PY'
import hashlib,json,os,secrets
salt=secrets.token_hex(16); iterations=250000
pwd=os.environ['BPM_PASSWORD']
h=hashlib.pbkdf2_hmac('sha256',pwd.encode(),bytes.fromhex(salt),iterations).hex()
cfg={
  'bind':os.environ['BPM_BIND'], 'port':int(os.environ['BPM_PORT']),
  'database':'/var/lib/backpack-manager/manager.db',
  'backpack_config_dir':'/etc/backpack', 'poll_interval_seconds':15, 'log_level':'INFO',
  'auth':{'username':os.environ['BPM_USER'],'salt':salt,'password_hash':h,'iterations':iterations}
}
with open(os.environ['CFG'],'w') as f: json.dump(cfg,f,indent=2)
os.chmod(os.environ['CFG'],0o600)
PY
  CREDS_FILE="$ETC_DIR/initial-credentials.txt"
  printf 'username=%s\npassword=%s\n' "$BPM_USER" "$BPM_PASSWORD" > "$CREDS_FILE"
  chmod 0600 "$CREDS_FILE"
else
  echo "Keeping existing $CFG"
fi

cat > "$UNIT" <<'EOF'
[Unit]
Description=BackPack Manager (download-only tunnel quotas)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/backpack-manager
Environment=PYTHONPATH=/opt/backpack-manager
ExecStart=/usr/bin/python3 -m backpack_manager --config /etc/backpack-manager/config.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full
ReadWritePaths=/etc/backpack /etc/backpack-manager /var/lib/backpack-manager /run /var/run

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now backpack-manager.service
sleep 1
systemctl --no-pager --full status backpack-manager.service || true

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
PORT=$(python3 -c 'import json; print(json.load(open("/etc/backpack-manager/config.json"))["port"])')
echo
echo "Installed."
echo "Panel: http://${IP:-SERVER_IP}:${PORT}/"
echo "Credentials: /etc/backpack-manager/initial-credentials.txt"
echo "Logs: journalctl -u backpack-manager -f"
echo "Runtime requires no PyPI packages and no external API, so it works after installation even if the server has restricted international access."
