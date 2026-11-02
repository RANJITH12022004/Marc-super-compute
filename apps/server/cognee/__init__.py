"""Marc cognee memory adapter (stdlib-first, local-only).

Local wrapper Marc can call without a public port.

- No listeners, no public Bind, no Needle / ollama / laya.
- Stdlib only for the fallback path; ``cognee`` package is optional.
- ``COGNEE_DATA_DIR`` env (default ``./var/cognee``) is ensured to exist.
- Telemetry concept: we never phone home. Conceptually
  ``TELEMETRY_DISABLED=true`` — no analytics, no outbound calls from
  this module. The in-process fallback makes zero network calls.
- Secret hygiene (vault-like): lines containing Authorization / Bearer /
  api-key / MARC_TOKEN / password are dropped before ingest, so secrets
  never reach cognee or the fallback store.
- Dataset isolation: ``personal`` hits never include ``project_*`` texts
  and vice versa. ``recall`` only searches the explicitly requested
  datasets (default ``personal``).
"""

from .memory import forget, recall, remember

__all__ = ["remember", "recall", "forget"]
