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

## Live `marc_api.py` patch

Paste `plan_with_muse.py` into `marc_api.py`, set `MARC_PLANNER=muse`,
and call `plan_with_muse()` instead of `plan_with_needle()`. That is the
only live mark-laptop / Rox source edit.

## Phone leftover

See [../phone/LEFTOVER.md](../phone/LEFTOVER.md). Fast LocalMarc phrases stay
on-device. Needle `:18096` stays off. Copy [../phone/needle-off.env](../phone/needle-off.env).

## Security

- Binds `127.0.0.1:8096` only; do not add `ListenStream` / firewall rules for it.
- Keep `MARC_MODE=sandbox` until you explicitly flip live.
