# VPS runbook: publish the web app over HTTPS

Copy-paste steps for an Ubuntu 24.04 VPS. Written against Caddy 2 from the
official apt repo and frp v0.61.0. Design background:
[`docs/superpowers/specs/2026-09-12-web-app-design.md`](../superpowers/specs/2026-09-12-web-app-design.md)
sections 4 and 11.

The VPS is infrastructure only. It runs two binaries (Caddy, `frps`) with two
config files and holds no application code, database, sheet or password. If it
is lost, repeat this page on a fresh machine; nothing needs restoring.

```
 phone / browser ── https://<host> ──> Caddy :443 ──> 127.0.0.1:8000 on the VPS
                                                          ^
                                          frps :7000 <────┘  (loopback only)
                                            ^
                          outbound TLS tunnel from the PC (frpc)
                                            |
                                  PC: server.py on 127.0.0.1:8000
```

Throughout, replace `<host>` with your hostname and `<vps-ip>` with the VPS
public IPv4 address.

## Before you start

- A VPS with Ubuntu 24.04, a public IPv4, and SSH access as a user with `sudo`.
- Ports **80, 443, 7000** reachable from the internet (check the provider's
  cloud firewall as well as `ufw`; both must allow them).
- A hostname for `<host>`, one of:
  - your own domain: an `A` record pointing at `<vps-ip>` (wait until
    `dig +short <host>` prints the IP before step 1), or
  - no domain: use `<vps-ip>.sslip.io` (for `203.0.113.10` that is
    `203.0.113.10.sslip.io`). It resolves to the IP by itself; nothing to set up.
- On the PC: the Python packages from `requirements.txt` (`INSTALL.bat`) and
  Node 24 for `BUILD_WEB.bat`.

## 1. VPS: Caddy (HTTPS in front of the tunnel)

Install from Caddy's own apt repository (the Ubuntu package lags):

```bash
sudo apt update
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Replace the default Caddyfile. Caddy obtains the certificate from Let's
Encrypt on first load and renews it by itself; `reverse_proxy` forwards
WebSocket upgrades (`/ws`) and sets `X-Forwarded-For` / `X-Forwarded-Proto`,
which the server relies on, so nothing else is needed:

```bash
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
<host> {
    encode zstd gzip
    header Strict-Transport-Security "max-age=31536000"
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -n 20 --no-pager
```

The journal should show `certificate obtained successfully` within a minute.
`obtaining certificate ... failed` means `<host>` does not resolve to this
machine yet or port 80 is blocked (the HTTP challenge needs it).

## 2. VPS: frps (tunnel endpoint)

Install the binary:

```bash
FRP=0.61.0
cd /tmp
curl -fsSLO "https://github.com/fatedier/frp/releases/download/v${FRP}/frp_${FRP}_linux_amd64.tar.gz"
tar xzf "frp_${FRP}_linux_amd64.tar.gz"
sudo install -m 755 "frp_${FRP}_linux_amd64/frps" /usr/local/bin/frps
frps --version
```

Generate the tunnel token and keep the output; the PC needs the same value:

```bash
openssl rand -hex 32
```

Write the config. `proxyBindAddr` keeps the tunnelled port on loopback so the
app is reachable only through Caddy; `allowPorts` stops anyone holding the
token from opening other ports; `transport.tls.force` refuses a plaintext
client:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin frp
sudo mkdir -p /etc/frp
sudo tee /etc/frp/frps.toml >/dev/null <<'EOF'
bindPort = 7000
auth.method = "token"
auth.token = "PASTE-THE-64-HEX-CHARACTERS-HERE"
transport.tls.force = true
proxyBindAddr = "127.0.0.1"
allowPorts = [{ single = 8000 }]
EOF
sudo chown root:frp /etc/frp/frps.toml
sudo chmod 640 /etc/frp/frps.toml
```

Run it as a service under the unprivileged `frp` user:

```bash
sudo tee /etc/systemd/system/frps.service >/dev/null <<'EOF'
[Unit]
Description=frp server - tunnel endpoint for AutoShare
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=frp
Group=frp
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5
LimitNOFILE=65536
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now frps
sudo systemctl status frps --no-pager
```

## 3. VPS: firewall

Allow SSH first or the next command locks you out:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443,7000/tcp
sudo ufw --force enable
sudo ufw status
```

## 4. VPS: check before touching the PC

```bash
sudo ss -ltnp | grep -E ':(80|443|7000) '
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/api/health
```

Expect three listeners, and **502** from the second command: TLS works and
Caddy is up, but nothing is behind the tunnel yet. A certificate error here
belongs to step 1, a timeout to step 3.

## 5. PC: password, frontend build, tunnel client

In a terminal at the repo root:

```bat
INSTALL.bat                          rem installs fastapi, uvicorn, bcrypt, itsdangerous from requirements.txt
python scripts\set_web_password.py   rem the one operator password; asked twice, 8+ characters
BUILD_WEB.bat                        rem npm ci && npm run build -> web\dist
```

`server.py` refuses to start until a password hash exists;
`python scripts\set_web_password.py --check` tells you whether one does.

Install the tunnel client (details in [`tools/frp/README.md`](../../tools/frp/README.md)):

1. Download `frp_0.61.0_windows_amd64.zip` from
   https://github.com/fatedier/frp/releases/tag/v0.61.0 and copy `frpc.exe`
   from it into `tools\frp\`.
2. `copy tools\frp\frpc.example.toml tools\frp\frpc.toml`
3. In `tools\frp\frpc.toml` set `serverAddr = "<vps-ip>"` and paste the token
   from step 2 into `auth.token`. Both files are gitignored.

Start everything:

```bat
SERVER.bat
```

Two windows open: `frpc` (must print `login to server success` and
`[autoshare-web] start proxy success`) and `server.py`. Leave both running;
until phase 3 adds Task Scheduler entries, start `SERVER.bat` by hand after a
reboot.

## 6. Check end to end

Three checks, each one layer further out, so a failure names its layer:

```bat
curl http://127.0.0.1:8000/api/health        rem on the PC: server.py itself
```

```bash
curl http://127.0.0.1:8000/api/health        # on the VPS: the tunnel
curl https://<host>/api/health               # from anywhere: Caddy + tunnel
```

All three print `{"ok":true,"version":"<git short sha or dev>"}`.

## 7. Phone and desktop install

- **iPhone**: in Safari open `https://<host>`, log in, tap Share (the square
  with the arrow), then **Add to Home Screen**, then **Add**. Safari only:
  in-app browsers (Messenger, Gmail) do not offer it.
- **Android**: in Chrome open `https://<host>`, menu (three dots) then
  **Install app** or **Add to Home screen**.
- **Windows / Mac**: Chrome or Edge show an install icon at the right end of
  the address bar.

The installed icon keeps its own cookies, separate from the browser, so log in
once more inside it. The session lasts 30 days; the same password logs in on
every device. iOS installs a web app and registers its service worker only
from HTTPS, which is why the VPS exists.

## 8. Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `502 Bad Gateway`, or the app shows "PC unreachable - reconnecting" | nothing behind the tunnel: PC off or asleep, `SERVER.bat` not running, `frpc` disconnected, `server.py` crashed | on the PC look at both windows, then run the three checks in step 6 from the inside out |
| browser certificate warning; Caddy journal says `obtaining certificate ... failed` | `<host>` does not resolve to `<vps-ip>`, or port 80 is closed (Let's Encrypt HTTP challenge) | `dig +short <host>`; `sudo ufw status` and the provider firewall; `sudo journalctl -u caddy -n 50` |
| certificate for a `*.sslip.io` name refused with a rate-limit message | Let's Encrypt caps certificates per registered domain and sslip.io is shared by everyone | Caddy retries with ZeroSSL on its own; wait a few minutes, or use your own domain |
| login succeeds, the very next request is `401` again (login loop) | the PC clock jumped: session tokens are timestamped and a token "from the future" is rejected. Or the cookie was never stored: it is `Secure`, so plain `http://` drops it | sync the PC clock (Settings > Time & language > Sync now), then log in again; always use `https://<host>`; for `npm run dev` start the server with `--dev` |
| `429` on the login page | five wrong passwords within 15 minutes from one address | wait 15 minutes, or restart `server.py` (the counter lives in memory) |
| every button answers `403` | Origin check: the browser's `Origin` differs from what uvicorn believes its host is | set the public host and restart: `python -c "from src.storage import config_manager as cfg; cfg.save_setting('web_public_host', 'https://<host>')"` |
| frpc: `login to server failed` mentioning `token` | `auth.token` differs between `frps.toml` and `frpc.toml` | paste the same 64 hex characters into both |
| frpc: `dial tcp <vps-ip>:7000 ... timeout` or `connection refused` | port 7000 blocked, or `frps` not running | `sudo ufw status`; `sudo systemctl status frps` |
| frpc: `port not allowed` | `remotePort` is outside `allowPorts` in `frps.toml` | keep both at 8000 |
| frpc: `proxy [autoshare-web] already exists` | an older `frpc` window is still connected | close the old `SERVER.bat` windows first |
| page says `web/dist not built - run BUILD_WEB.bat` | server started before the frontend was built | `BUILD_WEB.bat`, then reload |
| "Add to Home Screen" missing on iPhone | not HTTPS, or not Safari | open `https://<host>` in Safari |

Server-side log lines (the same ones the desktop Log tab shows) are in
`~/.autoshare/logs/app-YYYYMMDD.log` on the PC.

## 9. Rotating secrets, rebuilding

- **Tunnel token**: `openssl rand -hex 32`, put it in `/etc/frp/frps.toml`,
  `sudo systemctl restart frps`, put it in `tools\frp\frpc.toml`, restart
  `SERVER.bat`.
- **Web password**: `python scripts\set_web_password.py` again. Devices that
  are already logged in stay logged in, because sessions are signed with a
  separate secret. To log every device out, stop the server, remove the
  `web_session_secret` line from `~/.autoshare/config.json`, and start it
  again; a new secret is generated on the first request.
- **New VPS**: repeat steps 1-4 with the same `<host>` (or update the `A`
  record), then change `serverAddr` in `frpc.toml`. Nothing else on the PC
  changes.

## 10. What is where

| VPS | purpose |
|---|---|
| `/etc/caddy/Caddyfile` | the one site block from step 1 |
| `/var/lib/caddy/` | certificates, managed by Caddy |
| `/usr/local/bin/frps`, `/etc/frp/frps.toml`, `/etc/systemd/system/frps.service` | tunnel endpoint; `frps.toml` holds the token |

| PC | purpose |
|---|---|
| `tools\frp\frpc.exe`, `tools\frp\frpc.toml` | tunnel client; `frpc.toml` holds the token (gitignored) |
| `~\.autoshare\config.json` | `web_password_hash`, `web_session_secret`, optional `web_public_host` |
| `~\.autoshare\logs\app-YYYYMMDD.log` | server log, one file per day |
| `web\dist\` | the frontend build `server.py` serves (gitignored) |
