"""Ingest markdown mind-tree files into the local cognee memory (stdlib only).

Walks ``.md`` files under the given paths and stores them via
:func:`apps.server.cognee.memory.remember` into ``personal_dataset``.

Skipped (never read, never stored) when the file name contains:
``secret``, ``.env``, ``google_token``, ``token.json``, or matches
``*.pem``. Matching is case-insensitive on the basename.
"""

import os

_SKIP_SUBSTRINGS = ("secret", ".env", "google_token", "token.json")


def _should_skip(name):
    lowered = (name or "").lower()
    if lowered.endswith(".pem"):
        return True
    return any(marker in lowered for marker in _SKIP_SUBSTRINGS)


def _iter_md_files(paths):
    seen = []
    if isinstance(paths, (str, bytes, os.PathLike)):
        paths = [paths]
    try:
        items = list(paths or [])
    except TypeError:
        return seen
    for raw in items:
        path = os.fspath(raw) if isinstance(raw, os.PathLike) else str(raw)
        if not path:
            continue
        if os.path.isfile(path):
            if path.lower().endswith(".md") and not _should_skip(os.path.basename(path)):
                seen.append(path)
            continue
        if not os.path.isdir(path):
            continue
        for root, _dirs, files in os.walk(path):
            for fname in files:
                if not fname.lower().endswith(".md"):
                    continue
                if _should_skip(fname):
                    continue
                seen.append(os.path.join(root, fname))
    return seen


def ingest_mind_trees(paths, personal_dataset="personal"):
    """Walk md files under ``paths`` and remember them into ``personal_dataset``.

    Stdlib only. Returns ``{ok, files, skipped}``.
    """
    from .memory import remember

    dataset = str(personal_dataset or "personal")
    files = _iter_md_files(paths)
    count = 0
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue
        if not content.strip():
            continue
        remember(content, dataset=dataset)
        count += 1
    return {"ok": True, "files": count, "skipped": len(files) - count}
