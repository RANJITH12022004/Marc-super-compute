# MARC Demo — 90-Second Checklist

Live hands-free demo. No secrets in this file — placeholders only.

## Demo env (live on stage, sandbox in tests)

```bash
MARC_MODE=live
MARC_CONTEXT=driving
MARC_SKIP_NEEDLE=1
```

> `MARC_MODE=live` is for the demo only. Tests stay `sandbox`.
> `MARC_CONTEXT=driving` keeps replies short and confirms before acting.
> `MARC_SKIP_NEEDLE=1` skips the needle / safety download for the fast demo path.

Copy the full snippet from `env.example` — tokens are empty placeholders.

## Pre-flight (before timer starts)

- [ ] Laptop + phone on same network.
- [ ] Copy `deploy/demo/env.example` to `.env` and fill `MARC_TOKEN=` placeholder (do not commit secrets).
- [ ] `CONFIRM_TOOLS` includes send/dial actions so Marc asks before sending.

## 90-second checklist

1. **Start marc-muse** (0:00)
   ```bash
   MARC_MODE=live MARC_CONTEXT=driving MARC_SKIP_NEEDLE=1 python apps/marc-muse/server.py
   ```
   Expect: planner `muse` online at `http://127.0.0.1:8096`.

2. **Start laptop shell fake-mic** (0:10)
   ```bash
   set PYTHONPATH=apps
   python -m marc_shell --fake-mic --context driving
   ```
   Expect: fake-mic replays the demo utterances against `http://127.0.0.1:8096`.

3. **Phone island APK** (0:20)
   - Install / open the island APK on the phone.
   - Point it at `MARC_MUSE_URL` and confirm connected (island shows idle).

4. **Wake Hey Marc** (0:30)
   - Say **"Hey Marc"**.
   - Expect: island wakes, laptop hears wake tone.

5. **Compound utterance** (0:40)
   - Say one compound request, e.g. **"Hey Marc, summarize my inbox and text Mom I'll be late"**.
   - Expect: Marc plans multi-step, speaks a short driving-style summary, then asks to confirm sends.

6. **Say yes** (0:55)
   - Say **"yes"** to confirm.
   - Expect: confirmed tools run, Marc speaks done.

7. **Open VS Code on laptop** (1:05)
   - Show the laptop: Marc log / VS Code with the executed result (mail draft, message log, calendar entry).
   - Expect: audience sees action landed.

8. **Stop Marc** (1:20)
   - Say **"stop Marc"** or Ctrl+C both processes.
   - Expect: island back to idle, servers stopped.

## If it fails on stage

- No wake? Check fake-mic is running and `MARC_MUSE_URL` / `MARC_LAPTOP_URL` placeholders match your LAN IPs.
- No plan? Check `MARC_PLANNER=muse` and server logs.
- Slow needle? Confirm `MARC_SKIP_NEEDLE=1` is set.
