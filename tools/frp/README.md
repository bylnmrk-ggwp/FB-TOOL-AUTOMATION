# tools/frp - the PC end of the VPS tunnel

`frpc.exe` keeps one outbound, token-authenticated, TLS-encrypted connection
from this PC to `frps` on the VPS, so `https://<host>` reaches `server.py`
without opening any inbound port on the PC or the router. The full procedure,
VPS side included, is [docs/runbooks/vps.md](../../docs/runbooks/vps.md).

What lives here:

| file | committed | purpose |
|---|---|---|
| `frpc.example.toml` | yes | template: copy to `frpc.toml`, fill in the VPS address and token |
| `frpc.toml` | no (gitignored) | holds the tunnel token, so treat it as a credential |
| `frpc.exe` | no (gitignored) | the client binary from the frp Windows release, see below |

Install:

1. Download `frp_0.61.0_windows_amd64.zip` from
   https://github.com/fatedier/frp/releases/tag/v0.61.0 (the version the
   runbook was written against) and copy only `frpc.exe` out of it into this
   folder. The zip's `frps.exe` is the server side and is not used on the PC.
2. `copy frpc.example.toml frpc.toml`, then set `serverAddr` and `auth.token`.
3. Run `SERVER.bat` from the repo root: it opens `frpc` in its own window when
   both files exist, then starts `python server.py`.

To check the tunnel on its own, run `tools\frp\frpc.exe -c tools\frp\frpc.toml`
from the repo root. `login to server success` followed by
`[autoshare-web] start proxy success` means the address, token and TLS
settings all match the VPS.
