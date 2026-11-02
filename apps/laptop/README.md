# MARC laptop worker (Windows, no model)

Small stdlib-only Python HTTP worker for the Windows laptop. No ML, no `bee-island` imports.

## Endpoints

- `GET /health` → `{"ok": true, "device": "laptop"}`
- `POST /run` with JSON `{"tool": ..., "args": {...}}`
  - Allowlist only: `open_app`, `type_into`. Everything else is refused with `{"ok": false, ...}`.
  - `open_app`: calls Windows `os.startfile(label)` on the laptop. Refuses `reboot`/`shutdown`/`sudo`/`rm`-style tools and labels.
  - `type_into`: simulated in sandbox (`MARC_MODE=sandbox` returns `ok:true`). Live mode returns `ok:false` until a `pyautogui` implementation lands.

## Start

```powershell
cd apps\laptop
python worker.py
```

Optional env:

```powershell
$env:MARC_LAPTOP_PORT = "8765"   # default 8765; always binds 0.0.0.0
$env:MARC_TOKEN = "..."          # optional shared secret
$env:MARC_MODE = "sandbox"       # set for safe local testing (simulates side effects)
python worker.py
```

When `MARC_TOKEN` is set, send it as `X-MARC-Token` (or `X-Token`, or `Authorization: Bearer <token>`, or JSON body `token` field).

## Rox wiring

Point Rox at the laptop over Tailscale:

```text
MARC_LAPTOP_URL=http://<tailscale-ipv4>:8765
```

Rox then `POST`s to `<MARC_LAPTOP_URL>/run`. Health check: `GET <MARC_LAPTOP_URL>/health`.

## Tests

```powershell
python -m pytest apps\laptop\tests\test_worker.py -q
```

## Security notes

- No secrets in git. `MARC_TOKEN` comes from the environment only.
- Bind is `0.0.0.0:<port>` — rely on Tailscale ACL / Windows firewall for access control.
- `bee-island` is never imported (tested).
