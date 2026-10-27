# Marc Ride — Hackathon Slice Spec

**Slice:** Marc Ride driving demo
**Window:** Oct 27 – Nov 4, 2026
**Stack:** Phone Dynamic Island + laptop wake-word shell + Rox `marc-muse`
**Status:** Hackathon demo slice (not the full Marc PRD)

## 1. What this slice is

Hands-free Marc for a two-wheeler commute. Phone shows a
Dynamic Island pill, laptop runs a wake-word shell for desk
prep, and all leftover planning happens in `marc-muse` on Rox.

Out of scope: new helmet hardware, full Marc desk, Office loops.

## 2. Surfaces (3 only)

| Surface | Job |
|---------|-----|
| Phone Dynamic Island | Mic, pill states, spoken replies, Yes/No voice confirm |
| Laptop wake-word shell | `Hey Marc` listener, types / opens apps, no model |
| Rox `marc-muse` | Sole planner for leftover utterances |

## 3. Helmet = software driving mode

Helmet is **SOFTWARE driving mode**, not new firmware.

- Bluetooth mic + speaker is the only helmet gear.
- Driving mode = short replies, louder TTS, voice confirm.
- No flashing, no custom PCB, no firmware work in this slice.

## 4. Context + mode env

- `MARC_CONTEXT=desk|driving`, default `desk`.
- `MARC_MODE=sandbox|live`, default `sandbox`.
- `MARC_SKIP_NEEDLE=1` — Needle path is off for this slice.
- Desk behavior unchanged when `MARC_CONTEXT=desk`.
- Driving mode shortens replies and forces voice confirm.

## 5. Safety: no silent auto-send

- Nothing sends without an explicit voice confirm.
- Driving confirm words: `yes` / `send it` to confirm, `cancel` to drop.
- Sandbox queues drafts; live sends only after spoken confirm.
- Applies to mail, WhatsApp, dial, and any external send.

## 6. Dynamic Island states

States: `idle` / `listen` / `plan` / `wave` / `confirm` / `done` / `fail`.

- `idle`: pill parked at camera cutout, no text.
- `listen`: pulsing, shows `Listening…`
- `plan`: shows `Planning…`
- `wave`: mini waveform while user speaks.
- `confirm`: shows confirm question + Yes / No hint.
- `done`: one-line result, auto-dismiss.
- `fail`: one-line failure, auto-dismiss.
- Every pill line is `<= 40 chars`.
- **Overlay geometry frozen** — no resize, no reposition.

## 7. Ephemeral agents (per-turn only)

Each turn spawns short-lived agents, then drops them:

- `mail` — compose / draft recap mail, confirm-gated.
- `whatsapp` — prefill / draft text, confirm-gated.
- `dial` — dial contact / number, confirm-gated.
- `music` — Spotify play / playlist, no confirm.
- `laptop` — open / type / search via worker, no model.

No agent persists state; `marc-muse` plan is the record.

## 8. Fast path vs planner

Local regex runs first and **skips Muse** for:

- `open Spotify` / `play <playlist>` → `music` agent.
- `type <text>` / `send it` → type / submit.
- `youtube <query>` → open + search.

Everything else goes to `marc-muse` for a planned tool call.

## 9. Hop caps

- Driving (`MARC_CONTEXT=driving`): hop cap **6**.
- Desk (`MARC_CONTEXT=desk`): hop cap **8**.
- Over cap → stop, speak fail line, queue nothing.

## 10. Demo script (5 utterances)

1. `Hey Marc` → wake word, island `listen`, reply `I'm listening.`
2. `Text Amma I'll be home by 8, play the driving playlist, and email the hackathon recap to myself` → multi-step plan: whatsapp draft + music play + mail draft, then island `confirm`.
3. `yes` → confirms pending sends, island `done`.
4. `Open VS Code on my laptop and type the demo notes` → `laptop` agent via wake-word shell.
5. `stop Marc` → halt turn, island `idle`.

Confirm wording example (<= 40 chars):

- `Text Amma? Say yes or cancel.`
- `Send recap mail? Say send it.`
- `Done. Amma text + playlist on.`

## 11. Failure lines (<= 40 chars)

- `Muse isn't running.`
- `Laptop isn't connected.`
- `Draft saved. Say send to confirm.`
- `Cancelled. Nothing sent.`

## 12. Tests

- Tests stay on **offline fixtures** — no live mic, no cloud send.
- Fixture island states, fixture plans, fixture confirms.
- Assert: no auto-send, lines <= 40 chars, hop caps held.
