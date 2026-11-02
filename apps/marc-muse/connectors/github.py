"""GitHub connector — list repos + write mind digests (stdlib only).

Sandbox (no GITHUB_TOKEN or MARC_MODE!=live): FAKE fixtures, no network.
Live: GET /users/{login}/repos with Bearer token; write notes/github/*.md
and merge_me_facts GitHub section.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

__all__ = ["ingest_repos", "list_repos", "is_sandbox", "FAKE_REPOS"]

FAKE_REPOS = [
    {
        "name": "Marc-super-compute",
        "description": "FAKE: personal Marc stack",
        "html_url": "https://github.com/RANJITH12022004/Marc-super-compute",
        "language": "Python",
    },
    {
        "name": "demo-notes",
        "description": "FAKE: notes demo",
        "html_url": "https://github.com/RANJITH12022004/demo-notes",
        "language": "JavaScript",
    },
]


def _mode() -> str:
    return (os.environ.get("MARC_MODE") or os.environ.get("MODE") or "sandbox").strip().lower()


def _token() -> str:
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


def _user() -> str:
    return (os.environ.get("GITHUB_USER") or "RANJITH12022004").strip() or "RANJITH12022004"


def is_sandbox() -> bool:
    return _mode() != "live" or not _token()


def _mind_dir() -> Path:
    raw = (os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind").strip()
    return Path(raw or "./var/mind")


def _api_get(url: str, token: str) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer %s" % token,
            "User-Agent": "marc-muse",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def list_repos(limit: int = 30) -> list[dict]:
    """Return repo dicts (sandbox FAKE or live API)."""
    try:
        n = max(1, min(int(limit), 100))
    except Exception:
        n = 30
    if is_sandbox():
        return list(FAKE_REPOS)[:n]
    token = _token()
    user = _user()
    url = "https://api.github.com/users/%s/repos?per_page=%d&sort=updated" % (
        urllib.parse.quote(user),
        n,
    )
    try:
        data = _api_get(url, token)
    except Exception:
        return list(FAKE_REPOS)[:n]
    out = []
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "name": str(row.get("name") or ""),
                    "description": str(row.get("description") or ""),
                    "html_url": str(row.get("html_url") or ""),
                    "language": str(row.get("language") or ""),
                }
            )
    return out[:n]


def _safe_slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", (name or "").strip().lower()).strip("-")
    return (s or "repo")[:80]


def ingest_repos(limit: int = 30, mind_dir: str | Path | None = None) -> dict:
    """Write notes/github/*.md and merge ME.md GitHub section."""
    base = Path(mind_dir) if mind_dir else _mind_dir()
    notes = base / "notes" / "github"
    notes.mkdir(parents=True, exist_ok=True)
    repos = list_repos(limit=limit)
    lines = []
    written = 0
    for r in repos:
        name = r.get("name") or "repo"
        desc = r.get("description") or ""
        url = r.get("html_url") or ""
        lang = r.get("language") or ""
        body = "# %s\n\n- URL: %s\n- Language: %s\n- Description: %s\n" % (
            name,
            url,
            lang,
            desc or "(none)",
        )
        path = notes / ("%s.md" % _safe_slug(name))
        try:
            path.write_text(body, encoding="utf-8")
            written += 1
        except Exception:
            continue
        lines.append("- [[notes/github/%s]] — %s" % (_safe_slug(name), desc or name))
    section = "Repos:\n\n" + ("\n".join(lines) if lines else "- (none yet)")
    try:
        import sys

        muse = str(Path(__file__).resolve().parents[1])
        if muse not in sys.path:
            sys.path.insert(0, muse)
        from brain import vault as _vault  # type: ignore

        _vault.merge_me_facts({"github": section})
    except Exception:
        pass
    try:
        from brain import index as _idx  # type: ignore

        _idx.rebuild(base)
    except Exception:
        pass
    return {
        "ok": True,
        "mode": "sandbox" if is_sandbox() else "live",
        "written": written,
        "repos": [r.get("name") for r in repos],
    }
