# Mobile

One short page. No sources live here.

- **Live phone APK is `../bee-island`.** That is the source of truth for
  the on-phone app. Do not copy its sources here.
- **Laptop is `../laptop`.** Desk/dev loop lives there.
- **Server door/bridge is `../server`.** The Vercel-ready HTTPS mailbox
  (`door/`) pairs phone utterances with bridge results; no model, no
  audio, no chat history on the door.
- **`bee-android` is frozen.** Do not change it; reference only.

Flow: phone/laptop `POST /v1/utterance` -> door `GET /v1/pull`
(bridge) -> door `POST /v1/result` -> waiter wakes with
`{spoken, phone_steps, reply}`.
