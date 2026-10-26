# Phone leftover routing notes (MARC_PLANNER=muse)

## Scope

When `MARC_PLANNER=muse`, the phone overlay keeps a small set of
leftover/local routes handled by `LocalMarc`/regex instead of the
planner. Do not remove these routes unless the muse planner explicitly
covers them.

## Leftover commands (local, not planned)

The overlay still uses `LocalMarc`/regex for:

- `open Spotify` — local app-open intent.
- `type ...` — local keystroke/text injection.
- `youtube ...` — local YouTube search/open shortcut.

These match before planning and never reach `marc-muse`.

## Planned path (everything else)

All other leftover/assistant utterances:

1. Overlay `POST /utterance` to Rox.
2. Rox forwards to `marc-muse` on `:8096` (`MARC_MUSE_URL=http://127.0.0.1:8096`).
3. Muse response returns through Rox to the overlay.

## Needle must stay off

- Do NOT start on-device Needle on `:18096` in this mode.
- Keep `MARC_SKIP_NEEDLE=1` (see `needle-off.env`).
- Port `:18096` must remain free/unused; no health checks against it.

## Geometry freeze

- Do not change overlay geometry (position, size, margins, anchor).
- Routing-only change; no UI/layout edits.
- No Java source changes required for this note.

## Env (reference: `needle-off.env`)

```env
MARC_PLANNER=muse
MARC_SKIP_NEEDLE=1
MARC_MUSE_URL=http://127.0.0.1:8096
MARC_MODE=sandbox
```

## Rollback

Set:

```env
MARC_PLANNER=needle
```

and remove/unset `MARC_SKIP_NEEDLE=1` so the Needle path is used again.
