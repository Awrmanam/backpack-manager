#!/usr/bin/env bash
set -Eeuo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo "Run as root" >&2; exit 1; fi
systemctl disable --now backpack-manager.service 2>/dev/null || true
rm -f /etc/systemd/system/backpack-manager.service
systemctl daemon-reload
rm -rf /opt/backpack-manager
if [[ ${1:-} == "--purge" ]]; then rm -rf /etc/backpack-manager /var/lib/backpack-manager; else echo "Kept /etc/backpack-manager and /var/lib/backpack-manager. Use --purge to remove data."; fi
