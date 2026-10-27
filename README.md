# marc-workers + Muse Marc

This repo is both **marc-workers** (parallel Cursor-planned coding runs) and the **Muse Marc** agent source.

Cursor **plans**, Muse **codes in the terminal**. That spends [Meta Model API](https://dev.meta.ai) credits instead of Cursor usage peaks.

Live spec: [`docs/marc_prd.md`](docs/marc_prd.md) — read that before changing agent behavior.

Hackathon ride demo: [`docs/marc_ride_prd.md`](docs/marc_ride_prd.md) and the 90s checklist in [`deploy/demo/README.md`](deploy/demo/README.md).

- `apps/marc-muse` — Rox planner (Python, `:8096`).
- `deploy/rox` — systemd bundle for Rox (api, desk, muse, Office runner).
- `MARC_MODE=sandbox` by default. Don't run unconfined unless asked.

Do not force-push over old public IDE history.

## Setup

```bash
npm install
```

Set a Meta key (starts with `LLM_`):

```powershell
$env:MODEL_API_KEY = "LLM_..."
```

Or reuse a key already saved by the old Marc IDE in `%AppData%\Marc\secrets.dpapi.json`.

## How you work

In Cursor chat: plan the change, then write `.marc/job.json` (see [`.marc/job.example.json`](.marc/job.example.json)).

Each task must own **exclusive** files so workers do not collide.

```bash
node bin/marc-workers.mjs run
```

- Workers: `muse-spark-1.3` in parallel (default 3)
- Stitcher: `muse-wonder-1.0`
- Logs and diffs: `.marc/runs/<runId>/`
- Summary: `.marc/runs/<runId>/summary.md`

## Job shape

```json
{
  "goal": "one sentence",
  "constraints": ["node_modules"],
  "tasks": [
    {
      "id": "t1",
      "title": "short title",
      "files": ["src/foo.js"],
      "instructions": "what this worker may change"
    }
  ]
}
```

## Archived IDE

The Cursor-like desktop app was moved to `C:\Users\ranjith\Downloads\cursor replica` and remains at [github.com/RANJITH12022004/Marc-super-compute](https://github.com/RANJITH12022004/Marc-super-compute).
