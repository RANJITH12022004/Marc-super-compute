"""brain.recall — mind recall + note helpers (stdlib only).

mind_recall(query):
  - "who am i" / "whoami"  -> vault.who_am_i (fallback: identity files)
  - "what was i doing"     -> vault.what_was_i_doing (fallback: sessions/daily)
  - else                   -> index.search (fallback: keyword scan of mind dir)

mind_note(title, body):
  - project-like notes -> <mind>/projects/<slug>.md
  - everything else    -> <mind>/daily/YYYY-MM-DD.md (appended)

Both return JSON-able dicts shaped for GET /mind and GET /whoami:
  mind_recall -> {ok, text, hits}
  mind_note   -> {ok, text, path, hits}
"""

import datetime
import json
import os
import re
import sys
from pathlib import Path


def _mind_dir():
    try:
        import config as _cfg  # type: ignore

        if hasattr(_cfg, "load_settings"):
            try:
                return Path(_cfg.load_settings().mind_dir)
            except Exception:
                pass
    except Exception:
        pass
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    return Path(raw)


def _slug(text, default="note"):
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:80] or default


def _safe_read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _load_module(names):
    for name in names:
        try:
            __import__(name)
            mod = sys.modules.get(name)
            if mod is not None:
                return mod
        except Exception:
            continue
    return None


def _load_vault():
    return _load_module(("vault", "brain.vault", "marc-muse.vault"))


def _load_index():
    return _load_module(("index", "brain.index", "marc-muse.index"))


def _norm_result(res, default_text=""):
    """Normalize vault/index results to (text, hits)."""
    if res is None:
        return "", []
    if isinstance(res, str):
        return res, []
    if isinstance(res, dict):
        text = res.get("text", res.get("reply", res.get("output", ""))) or ""
        hits = res.get("hits", res.get("results", [])) or []
        if not isinstance(hits, list):
            hits = [hits]
        return str(text), hits
    if isinstance(res, (list, tuple)):
        hits = list(res)
        lines = []
        for h in hits[:8]:
            if isinstance(h, dict):
                lines.append(
                    str(h.get("snippet") or h.get("text") or h.get("path") or h)
                )
            else:
                lines.append(str(h))
        return "\n".join(lines), hits
    return str(res), []


def _identity_files(mind):
    names = ("whoami.md", "identity.md", "about.md", "me.md", "profile.md")
    found = []
    for n in names:
        for cand in (mind / n, mind / "projects" / n, mind / "daily" / n):
            try:
                if cand.is_file():
                    found.append(cand)
            except Exception:
                continue
    return found


def _who_am_i_text():
    mind = _mind_dir()
    vault = _load_vault()
    if vault is not None:
        for attr in ("who_am_i", "whoami", "who_am_i_text", "identity"):
            fn = getattr(vault, attr, None)
            if callable(fn):
                try:
                    text, hits = _norm_result(fn())
                    if text or hits:
                        return text, hits
                except TypeError:
                    try:
                        text, hits = _norm_result(fn(""))
                        if text or hits:
                            return text, hits
                    except Exception:
                        continue
                except Exception:
                    continue
    files = _identity_files(mind)
    if files:
        parts = []
        hits = []
        for p in files:
            body = _safe_read(p).strip()
            if not body:
                continue
            try:
                rel = str(p.relative_to(mind))
            except Exception:
                rel = p.name
            parts.append("## %s\n\n%s" % (rel, body))
            hits.append({"path": rel, "snippet": body[:240]})
        if parts:
            return "# who am i\n\n" + "\n\n---\n\n".join(parts), hits
    return (
        "# who am i\n\nI don't know who you are yet. "
        "Use `remember` / mind_note to save your name.",
        [],
    )


def _recent_sessions(mind, limit=5):
    sdir = mind / "sessions"
    items = []
    try:
        if sdir.is_dir():
            for p in sorted(
                sdir.glob("*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )[:limit]:
                raw = _safe_read(p).strip()
                if not raw:
                    continue
                try:
                    doc = json.loads(raw)
                except Exception:
                    continue
                reply = str(doc.get("reply") or "")[:300]
                try:
                    rel = str(p.relative_to(mind))
                except Exception:
                    rel = p.name
                items.append((rel, doc, reply))
    except Exception:
        pass
    return items


def _recent_daily(mind, limit=3):
    ddir = mind / "daily"
    out = []
    try:
        if ddir.is_dir():
            for p in sorted(
                ddir.glob("*.md"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )[:limit]:
                body = _safe_read(p).strip()
                if body:
                    try:
                        rel = str(p.relative_to(mind))
                    except Exception:
                        rel = p.name
                    out.append((rel, body[-1200:]))
    except Exception:
        pass
    return out


def _what_was_i_doing_text(limit=5):
    mind = _mind_dir()
    vault = _load_vault()
    if vault is not None:
        for attr in ("what_was_i_doing", "what_am_i_doing", "recent", "last_session"):
            fn = getattr(vault, attr, None)
            if callable(fn):
                try:
                    text, hits = _norm_result(fn())
                    if text or hits:
                        return text, hits
                except TypeError:
                    try:
                        text, hits = _norm_result(fn(limit))
                        if text or hits:
                            return text, hits
                    except Exception:
                        continue
                except Exception:
                    continue
    sessions = _recent_sessions(mind, limit=limit)
    daily = _recent_daily(mind, limit=3)
    if not sessions and not daily:
        return (
            "# what was i doing\n\nNo recent activity found.",
            [],
        )
    parts = ["# what was i doing", ""]
    hits = []
    for rel, doc, reply in sessions:
        sid = doc.get("session_id") or rel
        parts.append("- **%s**: %s" % (sid, reply or "(no reply)"))
        hits.append({"path": rel, "snippet": reply[:240]})
    for rel, body in daily:
        tail = body[-400:].replace("\n", " ").strip()
        parts.append("")
        parts.append("## %s\n\n...%s" % (rel, tail))
        hits.append({"path": rel, "snippet": tail[:240]})
    return "\n".join(parts).strip(), hits


def _collect_text_files(mind):
    exts = {".md", ".txt", ".json"}
    out = []
    try:
        if not mind.is_dir():
            return out
        for p in mind.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if p.suffix.lower() not in exts:
                    continue
                # Skip bulky session dumps? No — include, they are useful.
                if len(out) > 500:
                    break
                out.append(p)
            except Exception:
                continue
    except Exception:
        pass
    return out


def _snippet(body, low_body, tokens, width=240):
    idx = -1
    for tok in tokens:
        i = low_body.find(tok)
        if i >= 0 and (idx < 0 or i < idx):
            idx = i
    if idx < 0:
        chunk = body[:width].strip()
        return chunk
    start = max(0, idx - 80)
    chunk = body[start:start + width].strip()
    if start > 0:
        chunk = "..." + chunk
    if start + width < len(body):
        chunk = chunk + "..."
    return chunk.replace("\n", " ").strip() if len(chunk) < 600 else chunk[:600]


def _fallback_search(query, limit=5):
    mind = _mind_dir()
    q = (query or "").strip()
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", q) if len(t) >= 2]
    if not tokens:
        return (
            "# recall\n\nSay what to look up, e.g. `/mind?q=project`.",
            [],
        )
    scored = []
    for p in _collect_text_files(mind):
        body = _safe_read(p)
        if not body:
            continue
        low = body.lower()
        score = sum(low.count(t) for t in tokens)
        if score > 0:
            try:
                rel = str(p.relative_to(mind))
            except Exception:
                rel = p.name
            scored.append((score, rel, body, low))
    scored.sort(key=lambda r: r[0], reverse=True)
    top = scored[:limit]
    if not top:
        return ("# recall: %s\n\nNo matches found." % q, [])
    parts = ["# recall: %s" % q, ""]
    hits = []
    for score, rel, body, low in top:
        snip = _snippet(body, low, tokens)
        parts.append("## %s\n\n%s" % (rel, snip))
        parts.append("")
        hits.append({"path": rel, "snippet": snip})
    return "\n".join(parts).strip(), hits


def _index_search_text(query, limit=5):
    idx = _load_index()
    if idx is not None:
        for attr in ("search", "query", "lookup", "find"):
            fn = getattr(idx, attr, None)
            if callable(fn):
                try:
                    text, hits = _norm_result(fn(query))
                    if text or hits:
                        return text, hits
                except TypeError:
                    try:
                        text, hits = _norm_result(fn(query, limit))
                        if text or hits:
                            return text, hits
                    except Exception:
                        continue
                except Exception:
                    continue
    return _fallback_search(query, limit=limit)


def mind_recall(query=""):
    """Recall markdown for a query -> {ok, text, hits}."""
    q = query if isinstance(query, str) else str(query or "")
    low = q.lower()
    wants_who = ("who am i" in low or "whoami" in low or "who_am_i" in low)
    wants_doing = (
        "what was i doing" in low
        or "what am i doing" in low
        or "what i was doing" in low
        or "what_was_i_doing" in low
    )
    try:
        if wants_who and wants_doing:
            t1, h1 = _who_am_i_text()
            t2, h2 = _what_was_i_doing_text()
            return {"ok": True, "text": t1 + "\n\n---\n\n" + t2, "hits": list(h1) + list(h2)}
        if wants_who:
            text, hits = _who_am_i_text()
            return {"ok": True, "text": text, "hits": hits}
        if wants_doing:
            text, hits = _what_was_i_doing_text()
            return {"ok": True, "text": text, "hits": hits}
        if not q.strip():
            t1, h1 = _who_am_i_text()
            t2, h2 = _what_was_i_doing_text(limit=3)
            return {"ok": True, "text": t1 + "\n\n---\n\n" + t2, "hits": list(h1) + list(h2)}
        text, hits = _index_search_text(q)
        return {"ok": True, "text": text, "hits": hits}
    except Exception as exc:
        return {"ok": False, "text": "recall error: %s" % exc, "hits": []}


def mind_note(title="", body="", text="", **kw):
    """Write a note -> {ok, text, path, hits}.

    Accepts mind_note(title, body), mind_note(text=...), or
    mind_note({"text": ...}) shapes from the planner.
    """
    if isinstance(title, dict) and not body and not text:
        kw_text = title.get("text", title.get("body", ""))
        title = title.get("title", "")
        body = kw_text
    if kw:
        title = kw.get("title", title) or title
        body = kw.get("body", body) or body
        text = kw.get("text", text) or text
    title = str(title or "").strip()
    body = str(body or "").strip()
    text = str(text or "").strip()
    if text and not body:
        body = text
    if text and not title:
        title = text.split("\n")[0][:80].strip()
    if not title and body:
        first = body.split("\n")[0].strip().lstrip("# ").strip()
        title = first[:80] or "note"
    if not title:
        title = "note"
    if not body:
        body = title

    # Optional vault hook — never fatal.
    try:
        vault = _load_vault()
        if vault is not None:
            for attr in ("save_note", "add_note", "write_note", "note"):
                fn = getattr(vault, attr, None)
                if callable(fn):
                    try:
                        fn(title, body)
                        break
                    except TypeError:
                        try:
                            fn({"title": title, "body": body})
                            break
                        except Exception:
                            continue
                    except Exception:
                        break
    except Exception:
        pass

    low_t = title.lower()
    low_b = body.lower()
    is_project = (
        low_t.startswith("project:")
        or low_t.startswith("project/")
        or low_t.startswith("[project]")
        or low_b.startswith("#project")
        or "#project" in low_b
        or "project:" in low_t
    )
    mind = _mind_dir()
    try:
        if is_project:
            clean = re.sub(r"^(project\s*[:/\-]\s*|\[project\]\s*)", "", title, flags=re.I).strip() or "note"
            slug = _slug(clean)
            path = mind / "projects" / ("%s.md" % slug)
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = "# %s\n\n%s\n" % (clean, body)
            if path.is_file():
                existing = _safe_read(path)
                path.write_text(existing.rstrip() + "\n\n---\n\n" + entry, encoding="utf-8")
            else:
                path.write_text(entry, encoding="utf-8")
        else:
            day = datetime.date.today().isoformat()
            path = mind / "daily" / ("%s.md" % day)
            path.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.datetime.now().strftime("%H:%M")
            entry = "## %s %s\n\n%s\n" % (now, title, body)
            if path.is_file():
                existing = _safe_read(path)
                path.write_text(existing.rstrip() + "\n\n" + entry, encoding="utf-8")
            else:
                path.write_text("# %s\n\n%s" % (day, entry), encoding="utf-8")
        try:
            rel = str(path.relative_to(mind))
        except Exception:
            rel = path.name
        return {
            "ok": True,
            "text": "Saved to %s" % rel,
            "path": str(path),
            "hits": [{"path": rel}],
        }
    except Exception as exc:
        return {"ok": False, "text": "note error: %s" % exc, "path": "", "hits": []}


def who_am_i():
    """Convenience for GET /whoami -> {ok, text, hits}."""
    text, hits = _who_am_i_text()
    return {"ok": True, "text": text, "hits": hits}


__all__ = ["mind_recall", "mind_note", "who_am_i"]
