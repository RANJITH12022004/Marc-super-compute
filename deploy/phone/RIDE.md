# Phone leftover ride notes — mark-laptop patch

Leftover/phone overlay patch notes for the mark-laptop ride.
Routing-only change; no planner logic change.

## Overlay geometry — FROZEN

- Overlay geometry is FROZEN: do not change position, size, margins, or anchor.
- No UI/layout edits in this patch.

## Needle off

- Do NOT start on-device Needle on `:18096` in this mode.
- Keep `MARC_SKIP_NEEDLE=1`.
- Port `:18096` must remain free/unused; no health checks against it.

Reference env:

```env
MARC_PLANNER=muse
MARC_SKIP_NEEDLE=1
MARC_MUSE_URL=http://127.0.0.1:8096
MARC_MODE=sandbox
```

## Leftover regex — stay local

These match before planning and never reach `marc-muse`:

- `open Spotify` — local app-open intent.
- `type ...` — local keystroke/text injection.
- `youtube ...` — local YouTube search/open shortcut.

Do not remove these routes unless the muse planner explicitly covers them.

## Planned path — POST /utterance

All other leftover/assistant utterances:

- Overlay `POST /utterance` with JSON body:

```json
{ "text": "...", "context": {}, "source": "phone" }
```

- `text`: utterance string.
- `context`: driving / session context object.
- `source`: sender id (e.g. `phone`).
- Rox forwards to `marc-muse` on `:8096` (`MARC_MUSE_URL=http://127.0.0.1:8096`).
- Muse response returns through Rox to the overlay.

## Pill line — GET /island

- Overlay polls `GET /island` for the pill line.
- Render the returned line verbatim; no local reformatting.

## Driving context — voice yes/cancel

- Driving context supports voice confirm: `yes` confirms, `cancel` cancels.
- Keep hands-free flow: prompt → listen for yes/cancel → act.

## Laptop shell (mark-laptop)

Run from the laptop shell with fake mic:

```sh
PYTHONPATH=apps python -m marc_shell --fake-mic
```

## Rollback

Set:

```env
MARC_PLANNER=needle
```

and remove/unset `MARC_SKIP_NEEDLE=1` so the Needle path is used again.
