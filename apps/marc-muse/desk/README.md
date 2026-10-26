# Desk (Roxx)

Local web desk for Muse Marc.

Run:

```sh
python apps/marc-muse/server.py
```

Then open:

```
http://127.0.0.1:8096/desk
```

- Bind is loopback only (`127.0.0.1:8096`). Do not expose off-host.
- Sandbox only (`MARC_MODE=sandbox` default). Drafts never auto-send.
