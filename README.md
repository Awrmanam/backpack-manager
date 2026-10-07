# BackPack Manager

Independent, zero-PyPI-dependency manager for **download-only quotas** on [BackPack](https://github.com/AminMGMT/BackPack) tunnels.

## What it does

- Auto-discovers every existing `*.toml` tunnel in `/etc/backpack`.
- Keeps scanning, so tunnels created later in BackPack appear automatically.
- Reads BackPack's native `<name>.metrics.json`; it does not sniff packets and does not modify BackPack itself.
- Applies a quota to the **whole tunnel**. All forwarded ports inside that tunnel are already aggregated by BackPack's tunnel-level byte counters, so a 20-port tunnel has one shared download quota.
- Counts **download only**; upload is displayed but never deducted from quota.
- On an Iran-side reverse `server`, `bytes_in` is treated as download. On the reverse `client`, `bytes_out` is download. This can be overridden per tunnel.
- Stops only `backpack-<tunnel>.service` when its quota or expiry is reached.
- Preserves accounting across manager restarts and handles a metrics counter reset without losing already-accounted usage.
- Runs with Python stdlib + SQLite only; no pip packages, Redis, Docker, CDN or external API is required at runtime.

## Install

BackPack should already be installed. Then:

```bash
git clone https://github.com/Awrmanam/backpack-manager.git
cd backpack-manager
sudo ./install.sh
```

The installer prints the panel address and stores the generated initial credentials at:

```text
/etc/backpack-manager/initial-credentials.txt
```

Default panel port: `8787`.

Optional install environment variables:

```bash
sudo BPM_BIND=127.0.0.1 BPM_PORT=8787 BPM_USER=admin BPM_PASSWORD='strong-password' ./install.sh
```

The runtime does not need GitHub or any foreign service after installation, which makes it suitable for an Iran VPS. If the panel is exposed to the public Internet, put it behind HTTPS/restrict it with a firewall because HTTP Basic credentials must not travel over an untrusted plaintext network.

## How accounting works

BackPack writes one metrics file for one tunnel:

```text
/etc/backpack/customer-a.metrics.json
```

Those counters represent the tunnel as a whole, not individual forwarded ports. Therefore this manager intentionally never adds per-port counters or multiplies usage by the number of ports.

For a reverse tunnel:

| Manager location / role | Download counter | Free upload counter |
|---|---:|---:|
| Iran `server` | `bytes_in` | `bytes_out` |
| Remote `client` | `bytes_out` | `bytes_in` |

When you first save a quota, **Reset usage** is enabled by default, so old traffic that happened before selling/assigning the quota is not charged.

## Services / paths

```text
Service:  backpack-manager.service
App:      /opt/backpack-manager
Config:   /etc/backpack-manager/config.json
Database: /var/lib/backpack-manager/manager.db
BackPack: /etc/backpack/*.toml + *.metrics.json
```

Useful commands:

```bash
systemctl status backpack-manager
journalctl -u backpack-manager -f
systemctl restart backpack-manager
```

## Security model

The manager runs as root because it must read root-owned BackPack configs/metrics and start/stop `backpack-<name>.service`. It validates tunnel names before invoking `systemctl`, calls `systemctl` without a shell, never reads or displays BackPack tokens, and never rewrites BackPack TOML files.

## Uninstall

```bash
sudo ./uninstall.sh
```

This keeps manager config/database. To remove those too:

```bash
sudo ./uninstall.sh --purge
```
