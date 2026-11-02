# marc-muse on Rox

Loopback-only planner. Never expose `:8096` off loopback.

## Deploy

1. Copy the bundle to Rox:

   ```sh
   scp -r apps/marc-muse rox:/home/rox/marc-muse/apps/marc-muse
   scp deploy/rox/marc-muse.service rox:/tmp/marc-muse.service
   ```

2. Install the unit and configure env (`/home/rox/marc-muse.env`):

   ```sh
   sudo cp /tmp/marc-muse.service /etc/systemd/system/marc-muse.service
   cat >> /home/rox/marc-muse.env <<'EOF'
   MARC_PLANNER=muse
   MARC_MODE=sandbox
   MARC_MUSE_BIND=127.0.0.1
   MARC_MUSE_PORT=8096
   EOF
   ```

3. Enable and start:

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now marc-muse
   systemctl status marc-muse
   curl -s http://127.0.0.1:8096/health
   ```

## Bridge

Door pull -> loopback muse -> door result. The bridge never binds `:8096`
and only talks to `DOOR_URL` (https) plus loopback muse at
`http://127.0.0.1:8096`.

1. Copy the bridge to Rox:

   ```sh
   scp -r apps/server/bridge rox:/home/rox/marc-muse/apps/server/bridge
   scp deploy/rox/marc-bridge.service rox:/tmp/marc-bridge.service
   ```

2. Install the unit and set `DOOR_URL` + `MARC_TOKEN` in
   `/home/rox/marc-muse.env` (`DOOR_URL` is an https origin with no
   trailing slash):

   ```sh
   sudo cp /tmp/marc-bridge.service /etc/systemd/system/marc-bridge.service
   cat >> /home/rox/marc-muse.env <<'EOF'
   DOOR_URL=https://door.example.com
   MARC_TOKEN=change-me
   EOF
   ```

3. Enable and start (after `marc-muse`):

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now marc-bridge
   systemctl status marc-bridge
   ```

## Live `marc_api.py` patch

Paste `plan_with_muse.py` into `marc_api.py`, set `MARC_PLANNER=muse`,
and call `plan_with_muse()` instead of `plan_with_needle()`. That is the
only live mark-laptop / Rox source edit.

## Phone leftover

See [../phone/LEFTOVER.md](../phone/LEFTOVER.md). Fast LocalMarc phrases stay
on-device. Needle `:18096` stays off. Copy [../phone/needle-off.env](../phone/needle-off.env).

## Brain train (personal RAG)

Hybrid ingest (APIs/exports + one-shot phone Settings snapshot + laptop home walk).

1. **Tokens** (never commit): set `GITHUB_TOKEN`, Google token file via
   `GOOGLE_TOKEN_PATH` / `MARC_GOOGLE_TOKEN_PATH`, and `MARC_MODE=live` only when ready.
2. **Exports**: drop WhatsApp / Instagram export files, then:

   ```sh
   cd apps/marc-muse
   MARC_MIND_DIR=/home/rox/marc/mind python -m ingest_all --export /path/to/export.txt
   ```

3. **Hermes jobs** (loopback):

   ```sh
   curl -s -X POST http://127.0.0.1:8095/run \
     -H 'Content-Type: application/json' \
     -d '{"kind":"mind_ingest","source":"all","mind_dir":"/home/rox/marc/mind"}'
   curl -s -X POST http://127.0.0.1:8095/run \
     -H 'Content-Type: application/json' \
     -d '{"kind":"laptop_home_ingest","mind_dir":"/home/rox/marc/mind"}'
   ```

4. **Phone one-shot**: enable Accessibility, say “refresh my phone profile”
   (tool `phone_profile_snapshot`) → `notes/phone_settings_<date>.md`.
5. **Recall**: `/whoami`, `/mind?q=…`, and “what do you know about me?” are
   RAG-first over `mind.sqlite` + vault markdown.

## Security

- Binds `127.0.0.1:8096` only; do not add `ListenStream` / firewall rules for it.
- Bridge binds no ports; it only polls `DOOR_URL` and posts to loopback muse.
- Keep `MARC_MODE=sandbox` until you explicitly flip live.
