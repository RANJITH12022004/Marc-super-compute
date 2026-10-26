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
   MARC_MUSE_URL=http://127.0.0.1:8096/plan
   EOF
   ```

3. Enable and start:

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now marc-muse
   systemctl status marc-muse
   curl -s http://127.0.0.1:8096/plan -X POST -d '{}' -H 'Content-Type: application/json' | head -c 200
   ```

## Live `marc_api.py` patch

Paste `plan_with_muse.py` into `marc_api.py`, set `MARC_PLANNER=muse`,
and call `plan_with_muse()` instead of `plan_with_needle()`.

## Security

- Binds `127.0.0.1:8096` only; do not add `ListenStream` / firewall rules for it.
- Keep `MARC_MODE=sandbox`.
