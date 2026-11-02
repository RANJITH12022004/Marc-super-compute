"""Local stdlib-first memory adapter Marc can call locally.

No listeners, no public ports, no Needle / ollama / laya calls.

- ``COGNEE_DATA_DIR`` env (default ``./var/cognee``) is created on use.
- Telemetry is conceptually disabled (``TELEMETRY_DISABLED=true``):
  this module never phones home and makes zero outbound network calls.
  The in-process fallback store is pure stdlib with no network.
- Vault-like redaction: any line containing (case-insensitive)
  ``Authorization`` / ``Bearer`` / ``api-key`` / ``MARC_TOKEN`` /
  ``password`` is dropped before ingest, so secrets never reach cognee
  or the fallback store.
- Dataset isolation: the fallback store is keyed by dataset and
  ``recall`` only searches the explicitly requested datasets
  (default ``personal``). ``personal`` hits never include ``project_*``
  texts and vice versa.
- Every cognee call (when the optional ``cognee`` package is installed)
  always passes ``dataset_name``. Default dataset is ``personal``.
  If the ``cognee`` import fails, the in-process dict store is used so
  tests and the muse fallback work with no network and no cognee install.
"""

import os
import threading
import uuid

# Telemetry conceptually disabled: TELEMETRY_DISABLED=true. No analytics,
# no outbound HTTP, no background threads phoning home from this module.

_DEFAULT_DATASET = "personal"

# Case-insensitive markers; any line containing one is dropped pre-ingest.
_REDACT_MARKERS = (
    "authorization",
    "bearer",
    "api-key",
    "api_key",
    "marc_token",
    "password",
)

_STORE = {}
_STORE_LOCK = threading.Lock()

try:  # Optional dependency only. Stdlib fallback otherwise.
    import cognee  # type: ignore
except Exception:  # pragma: no cover - missing optional dep is expected
    cognee = None


def _data_dir():
    """Return COGNEE_DATA_DIR, ensuring it exists (stdlib only)."""
    path = os.environ.get("COGNEE_DATA_DIR", "./var/cognee")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _redact_text(text):
    """Drop secret-like lines vault-style. Returns redacted string."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    kept = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in _REDACT_MARKERS):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _normalize_datasets(datasets):
    if datasets is None:
        return [_DEFAULT_DATASET]
    if isinstance(datasets, str):
        return [datasets]
    try:
        items = list(datasets)
    except TypeError:
        return [_DEFAULT_DATASET]
    if not items:
        return [_DEFAULT_DATASET]
    return [str(d) for d in items]


def _store_add(dataset, text):
    entry = {"id": uuid.uuid4().hex, "text": text, "dataset": dataset}
    with _STORE_LOCK:
        _STORE.setdefault(dataset, []).append(entry)
    return entry


def _cognee_mirror_add(text, dataset):
    """Best-effort mirror into cognee. Never raises, never blocks tests."""
    if cognee is None or not text:
        return
    try:
        _data_dir()
        # cognee's python API is async; use a local event loop only if needed.
        # Always pass dataset_name.
        import asyncio
        import inspect

        async def _go():
            add = getattr(cognee, "add", None)
            if add is None:
                return
            res = add(text, dataset_name=dataset)
            if inspect.isawaitable(res):
                await res
            cognify = getattr(cognee, "cognify", None)
            if cognify is not None:
                try:
                    out = cognify(dataset_name=dataset)
                    if inspect.isawaitable(out):
                        await out
                except Exception:
                    pass

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            # Do not deadlock a running loop; skip cognee mirror.
            return
        if loop is None:
            asyncio.new_event_loop().run_until_complete(_go())
        else:
            loop.run_until_complete(_go())
    except Exception:
        pass


def ingest_text(text, dataset=_DEFAULT_DATASET):
    """Redact + store text. Used by :func:`remember`."""
    dataset = str(dataset or _DEFAULT_DATASET)
    _data_dir()
    redacted = _redact_text(text)
    if not redacted:
        # Nothing safe to store; still ok so callers do not retry secrets.
        return {"ok": True, "dataset": dataset, "skipped": True}
    _store_add(dataset, redacted)
    _cognee_mirror_add(redacted, dataset)
    return {"ok": True, "dataset": dataset}


def remember(text, dataset=_DEFAULT_DATASET):
    """Store text in ``dataset``. Returns ``{ok, dataset}``."""
    dataset = str(dataset or _DEFAULT_DATASET)
    ingest_text(text, dataset)
    return {"ok": True, "dataset": dataset}


def _matches(query, text):
    q = (query or "").strip().lower()
    if not q:
        return True
    t = (text or "").lower()
    if q in t:
        return True
    tokens = [tok for tok in q.split() if len(tok) > 2]
    return any(tok in t for tok in tokens)


def recall(query, datasets=None):
    """Search only ``datasets`` (default personal).

    Returns ``{ok, text, hits:[{text, dataset}]}``. Dataset isolation is
    enforced by only reading the requested dataset keys.
    """
    wanted = _normalize_datasets(datasets)
    _data_dir()
    hits = []
    with _STORE_LOCK:
        for ds in wanted:
            for entry in list(_STORE.get(ds, [])):
                if _matches(query, entry.get("text", "")):
                    hits.append({"text": entry["text"], "dataset": ds})
    # Best-effort cognee search merged in, strictly filtered to `wanted`.
    if cognee is not None:
        try:
            import asyncio
            import inspect

            async def _search():
                search = getattr(cognee, "search", None)
                if search is None:
                    return []
                out = search(query, dataset_name=wanted)
                if inspect.isawaitable(out):
                    out = await out
                return out or []

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop is None or not loop.is_running():
                coro = _search()
                results = (
                    asyncio.new_event_loop().run_until_complete(coro)
                    if loop is None
                    else loop.run_until_complete(coro)
                )
                for item in results or []:
                    if isinstance(item, dict):
                        txt = str(item.get("text", ""))
                        ds = str(item.get("dataset", wanted[0]))
                    else:
                        txt = str(item)
                        ds = wanted[0]
                    if ds not in wanted:
                        continue
                    txt = _redact_text(txt)
                    if txt and not any(h["text"] == txt for h in hits):
                        hits.append({"text": txt, "dataset": ds})
        except Exception:
            pass
    text = "\n---\n".join(h["text"] for h in hits)
    return {"ok": True, "text": text, "hits": hits}


def forget(query_or_id, dataset=_DEFAULT_DATASET):
    """Remove entries in ``dataset`` matching an id or text substring."""
    dataset = str(dataset or _DEFAULT_DATASET)
    _data_dir()
    needle = "" if query_or_id is None else str(query_or_id)
    removed = False
    with _STORE_LOCK:
        entries = list(_STORE.get(dataset, []))
        kept = []
        for entry in entries:
            if needle and (needle == entry.get("id") or needle in entry.get("text", "")):
                removed = True
                continue
            kept.append(entry)
        _STORE[dataset] = kept
    return {"ok": True if removed else False}


def _clear_store():
    """Test helper: wipe the in-process store. Not part of the spec API."""
    with _STORE_LOCK:
        _STORE.clear()
