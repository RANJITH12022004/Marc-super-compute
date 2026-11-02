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

inject_context(me, now, failed_lines):
  - clamped context block for prompts; drops Authorization/secrets.
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
    mod = _load_module(("vault", "brain.vault", "marc-muse.vault"))
    if mod is not None:
        return mod
    # File-location fallback: sibling vault.py (hyphenated pkg dir breaks imports).
    try:
        import importlib.util as _ilu  # stdlib only

        here = Path(__file__).resolve().parent
        for cand in (here / "vault.py", here.parent.parent / "vault.py"):
            try:
                if cand.is_file():
                    spec = _ilu.spec_from_file_location(
                        "_marc_muse_vault_fallback", str(cand)
                    )
                    if spec is not None and spec.loader is not None:
                        m = _ilu.module_from_spec(spec)
                        spec.loader.exec_module(m)  # type: ignore[union-attr]
                        return m
            except Exception:
                continue
    except Exception:
        pass
    return None


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


def _load_cognee_memory():
    """Optional Cognee wrapper. Never raises; markdown remains the fallback."""
    try:
        import importlib.util as _ilu

        here = Path(__file__).resolve()
        cand = here.parents[2] / "server" / "cognee" / "memory.py"
        if not cand.is_file():
            return None
        spec = _ilu.spec_from_file_location("_marc_cognee_memory", str(cand))
        if spec is None or spec.loader is None:
            return None
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _active_dataset():
    try:
        now = _safe_read(_mind_dir() / "NOW.md")
        m = re.search(r"^Project:\s*(\S+)", now or "", re.I | re.M)
        if m:
            slug = re.sub(r"[^a-z0-9_\-]+", "", m.group(1).strip().lower())
            if slug:
                return "project_" + slug
    except Exception:
        pass
    return "personal"


def _cognee_remember(text, dataset="personal"):
    mod = _load_cognee_memory()
    if mod is None:
        return
    fn = getattr(mod, "remember", None)
    if not callable(fn):
        return
    try:
        fn(text, dataset=dataset)
    except TypeError:
        try:
            fn(text, dataset)
        except Exception:
            return
    except Exception:
        return


def _cognee_recall(query, dataset="personal"):
    mod = _load_cognee_memory()
    if mod is None:
        return "", []
    fn = getattr(mod, "recall", None)
    if not callable(fn):
        return "", []
    try:
        res = fn(query, datasets=[dataset])
    except TypeError:
        try:
            res = fn(query, [dataset])
        except Exception:
            return "", []
    except Exception:
        return "", []
    if not isinstance(res, dict):
        return "", []
    text = str(res.get("text") or "")
    hits = res.get("hits") or []
    if not isinstance(hits, list):
        hits = []
    return text, hits


def _merge_cognee(query, text, hits, dataset=None):
    extra, extra_hits = _cognee_recall(query, dataset or _active_dataset())
    if extra and extra.strip() and extra.strip() not in (text or ""):
        text = (text or "") + "\n\n---\n\n" + extra.strip()
    if extra_hits:
        hits = list(hits or []) + list(extra_hits)
    return text, hits


def _rag_hits(query, limit=8):
    """Always hit FTS + recent messages before spoken output."""
    q = (query or "").strip() or "who am i"
    text, hits = _index_search_text(q, limit=limit)
    hits = list(hits or [])
    idx = _load_index()
    if idx is not None:
        fn = getattr(idx, "search_messages", None)
        if callable(fn):
            try:
                extra = fn(q, limit=limit)
            except TypeError:
                try:
                    extra = fn(q)
                except Exception:
                    extra = []
            except Exception:
                extra = []
            if isinstance(extra, list) and extra:
                parts = []
                for h in extra[:limit]:
                    if not isinstance(h, dict):
                        continue
                    snip = str(h.get("snippet") or "")[:240]
                    path = str(h.get("path") or "messages")
                    parts.append("## %s\n\n%s" % (path, snip))
                    hits.append(h)
                if parts:
                    block = "# chat memory\n\n" + "\n\n".join(parts)
                    if text and text.strip():
                        text = text.rstrip() + "\n\n---\n\n" + block
                    else:
                        text = block
    return text or "", hits


def _empty_brain_msg():
    return (
        "# brain empty\n\n"
        "Brain empty — run ingest (`python -m ingest_all`) "
        "or drop WA/IG exports, then reindex.",
        [],
    )


def mind_recall(query=""):
    """Recall markdown for a query -> {ok, text, hits}.

    RAG-first: always search mind.sqlite FTS (+ messages) before returning
    identity / utterance answers. Empty vault → honest empty message.
    """
    q = query if isinstance(query, str) else str(query or "")
    low = q.lower()
    wants_who = (
        "who am i" in low
        or "whoami" in low
        or "who_am_i" in low
        or "what do you know about me" in low
        or "know about me" in low
    )
    wants_doing = (
        "what was i doing" in low
        or "what am i doing" in low
        or "what i was doing" in low
        or "what_was_i_doing" in low
    )
    try:
        rag_q = q.strip() or ("who am i" if wants_who else "now")
        rag_text, rag_hits = _rag_hits(rag_q, limit=8)

        if wants_who and wants_doing:
            t1, h1 = _who_am_i_text()
            t2, h2 = _what_was_i_doing_text()
            text, hits = t1 + "\n\n---\n\n" + t2, list(h1) + list(h2)
        elif wants_who:
            text, hits = _who_am_i_text()
        elif wants_doing:
            text, hits = _what_was_i_doing_text()
        elif not q.strip():
            t1, h1 = _who_am_i_text()
            t2, h2 = _what_was_i_doing_text(limit=3)
            text, hits = t1 + "\n\n---\n\n" + t2, list(h1) + list(h2)
        else:
            text, hits = rag_text, rag_hits

        # Merge RAG hits ahead of planner/spoken output.
        if rag_text and rag_text.strip():
            if text and text.strip() and rag_text.strip() not in text:
                text = rag_text.rstrip() + "\n\n---\n\n" + text
                hits = list(rag_hits or []) + list(hits or [])
            elif not (text or "").strip():
                text, hits = rag_text, rag_hits
        elif not (hits or []) and not (text or "").strip():
            text, hits = _empty_brain_msg()
        elif wants_who and not rag_hits and "I don't know who you are" in (text or ""):
            text, hits = _empty_brain_msg()

        if not wants_who:
            try:
                text, hits = _merge_cognee(q or "now", text, hits)
            except Exception:
                pass
        return {"ok": True, "text": text, "hits": hits or []}
    except Exception as exc:
        return {"ok": False, "text": "recall error: %s" % exc, "hits": []}


# ------------------------------------------------- secrets + context ---

_AUTH_LINE_RE = re.compile(r"(?im)^[^\n]*authorization[^\n]*$")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-~+/=]+")
_TOKEN_VAL_RE = re.compile(r"(?i)(token\s*[:=]\s*)([A-Za-z0-9._\-~+/=]{8,})")


def _redact_secrets(text):
    """Drop Authorization material; redact bearer/token values. No logging."""
    try:
        s = text if isinstance(text, str) else str(text or "")
    except Exception:
        return ""
    try:
        # Drop whole lines mentioning authorization (headers, curl flags, etc).
        s = _AUTH_LINE_RE.sub("[redacted]", s)
        s = _BEARER_RE.sub("Bearer [redacted]", s)
        s = _TOKEN_VAL_RE.sub(lambda m: m.group(1) + "[redacted]", s)
        # Final sweep: ensure the word itself cannot leak a header value.
        # Keep it simple: remove case-insensitive "authorization" token.
        s = re.sub(r"(?i)authorization", "[redacted]", s)
    except Exception:
        pass
    return s


def _clamp(text, limit):
    try:
        s = text if isinstance(text, str) else str(text or "")
    except Exception:
        s = ""
    try:
        n = int(limit)
    except Exception:
        n = 1000
    if n <= 0:
        return ""
    s = s.strip()
    if len(s) > n:
        return s[: max(0, n - 12)].rstrip() + "…[truncated]"
    return s


def inject_context(me="", now="", failed_lines=None, max_chars=4000):
    """Build a clamped context block for prompts.

    Args:
      me: who-am-i markdown/text.
      now: NOW markdown/text.
      failed_lines: list of failure strings (or single string).
      max_chars: total clamp (default 4000).

    Drops Authorization/secrets and clamps each section so prompts stay
    bounded. Stdlib only; never logs secrets. Returns a string.
    """
    try:
        limit_total = int(max_chars)
    except Exception:
        limit_total = 4000
    if limit_total <= 0:
        limit_total = 4000
    limit_total = max(256, min(limit_total, 12000))

    try:
        me_s = me if isinstance(me, str) else str(me or "")
    except Exception:
        me_s = ""
    try:
        now_s = now if isinstance(now, str) else str(now or "")
    except Exception:
        now_s = ""

    if failed_lines is None:
        fails = []
    elif isinstance(failed_lines, str):
        fails = failed_lines.splitlines()
    elif isinstance(failed_lines, (list, tuple)):
        fails = []
        for item in failed_lines:
            try:
                if isinstance(item, str):
                    # Split embedded newlines so one entry cannot blow the clamp.
                    fails.extend(item.splitlines())
                elif item is None:
                    continue
                else:
                    fails.extend(str(item).splitlines())
            except Exception:
                continue
    else:
        try:
            fails = str(failed_lines).splitlines()
        except Exception:
            fails = []

    # Redact secrets before clamping so redaction cannot be cut off.
    me_s = _redact_secrets(me_s)
    now_s = _redact_secrets(now_s)
    clean_fails = []
    for line in fails:
        try:
            s = _redact_secrets(line).strip()
        except Exception:
            continue
        if not s:
            continue
        clean_fails.append(s)

    # Clamp sections: me/now bounded, failures bounded in count + width.
    me_s = _clamp(me_s, 1000)
    now_s = _clamp(now_s, 1000)
    max_failed = 8
    fail_width = 300
    trimmed = []
    for ln in clean_fails[:max_failed]:
        one = re.sub(r"\s+", " ", ln).strip()
        if len(one) > fail_width:
            one = one[: fail_width - 12].rstrip() + "…[truncated]"
        trimmed.append(one)

    parts = ["# Context", ""]
    if me_s:
        parts.append("## Me")
        parts.append("")
        parts.append(me_s)
        parts.append("")
    if now_s:
        parts.append("## Now")
        parts.append("")
        parts.append(now_s)
        parts.append("")
    if trimmed:
        parts.append("## Failed")
        parts.append("")
        for ln in trimmed:
            parts.append("- %s" % ln)
        parts.append("")
    out = "\n".join(parts).strip() + "\n"
    # Final safety: no Authorization substring may survive.
    out = re.sub(r"(?i)authorization", "[redacted]", out)
    out = _BEARER_RE.sub("Bearer [redacted]", out)
    if len(out) > limit_total:
        out = out[: max(0, limit_total - 12)].rstrip() + "…[truncated]\n"
    return out


def _vault_save_note(vault, title, body, rel, combined_text):
    """Call vault.save_note (preferred) or vault.write_md. Returns True if called."""
    # Preferred: save_note(title, body) — the persistent soul hook.
    for attr in ("save_note", "add_note", "write_note", "note"):
        try:
            fn = getattr(vault, attr, None)
        except Exception:
            fn = None
        if callable(fn):
            try:
                fn(title, body)
                return True
            except TypeError:
                try:
                    fn({"title": title, "body": body})
                    return True
                except Exception:
                    continue
            except Exception:
                # Vault hook must never break local persistence.
                return True
    # Fallback: write_md(rel, text) — same soul, markdown file.
    try:
        fn = getattr(vault, "write_md", None)
    except Exception:
        fn = None
    if callable(fn):
        try:
            # Prefer read-modify-write so write_md (overwrite) appends.
            existing = ""
            try:
                rfn = getattr(vault, "read_md", None)
                if callable(rfn):
                    existing = rfn(rel) or ""
            except Exception:
                existing = ""
            text_to_write = combined_text
            if existing and combined_text:
                # combined_text already includes existing when we built it
                # from local disk; if vault disk differs, merge vault side.
                try:
                    if combined_text.strip() not in (existing or ""):
                        sep = "" if (existing or "").endswith("\n") else "\n"
                        text_to_write = (existing or "") + sep + combined_text
                    else:
                        text_to_write = existing
                except Exception:
                    text_to_write = combined_text
            try:
                fn(rel, text_to_write)
            except TypeError:
                try:
                    fn({"path": rel, "text": text_to_write})
                except Exception:
                    return False
            return True
        except Exception:
            return False
    return False


def mind_note(title="", body="", text="", **kw):
    """Write a note -> {ok, text, path, hits}.

    Accepts mind_note(title, body), mind_note(text=...), or
    mind_note({"text": ...}) shapes from the planner.
    Persists via vault.save_note (or vault.write_md) plus a local
    markdown append so notes actually persist. Never logs secrets.
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

    # Redact secrets before persisting (never log secrets).
    title = _redact_secrets(title)
    body = _redact_secrets(body)
    if not title.strip():
        title = "note"
    if not body.strip():
        body = title

    low_t = title.lower()
    low_b = body.lower()
    is_phone_settings = low_t.startswith("phone_settings") or "phone_settings" in low_t
    is_project = (
        low_t.startswith("project:")
        or low_t.startswith("project/")
        or low_t.startswith("[project]")
        or low_b.startswith("#project")
        or "#project" in low_b
        or "project:" in low_t
    )
    mind = _mind_dir()
    if is_phone_settings:
        slug = _slug(title, "phone_settings")
        rel = "notes/%s.md" % slug
        path = mind / "notes" / ("%s.md" % slug)
        entry = "# %s\n\n%s\n" % (title, body)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(entry, encoding="utf-8")
        except Exception as exc:
            return {"ok": False, "text": "note error: %s" % exc, "path": "", "hits": []}
        try:
            vault = _load_vault()
            if vault is not None and hasattr(vault, "merge_me_facts"):
                snippet = body.strip().splitlines()
                preview = "\n".join(snippet[:12])[:600]
                vault.merge_me_facts({"phone": preview or title})
        except Exception:
            pass
        try:
            idx = _load_index()
            if idx is not None and hasattr(idx, "rebuild"):
                idx.rebuild(mind)
        except Exception:
            pass
        return {
            "ok": True,
            "text": "Saved to %s" % rel,
            "path": str(path),
            "hits": [{"path": rel}],
        }
    # Pre-compute rel + entry so vault.write_md can persist the same soul.
    if is_project:
        clean = re.sub(r"^(project\s*[:/\-]\s*|\[project\]\s*)", "", title, flags=re.I).strip() or "note"
        slug = _slug(clean)
        rel = "projects/%s.md" % slug
        path = mind / "projects" / ("%s.md" % slug)
        entry = "# %s\n\n%s\n" % (clean, body)
    else:
        day = datetime.date.today().isoformat()
        rel = "daily/%s.md" % day
        path = mind / "daily" / ("%s.md" % day)
        now = datetime.datetime.now().strftime("%H:%M")
        entry = "## %s %s\n\n%s\n" % (now, title, body)

    # MUST call vault.save_note (or write_md) so notes actually persist.
    # Build combined text for write_md-style vaults (overwrite semantic).
    combined_for_vault = entry
    try:
        existing_local = _safe_read(path)
        if existing_local.strip():
            if is_project:
                combined_for_vault = existing_local.rstrip() + "\n\n---\n\n" + entry
            else:
                if existing_local.startswith("#"):
                    combined_for_vault = existing_local.rstrip() + "\n\n" + entry
                else:
                    day = datetime.date.today().isoformat()
                    combined_for_vault = "# %s\n\n" % day + existing_local.rstrip() + "\n\n" + entry
        else:
            if not is_project and not entry.startswith("# "):
                day = datetime.date.today().isoformat()
                # entry already has day header only when file is new; keep as built below.
                pass
    except Exception:
        combined_for_vault = entry
    try:
        vault = _load_vault()
        if vault is not None:
            try:
                _vault_save_note(vault, title, body, rel, combined_for_vault)
            except Exception:
                pass
    except Exception:
        pass

    try:
        if is_project:
            clean = re.sub(r"^(project\s*[:/\-]\s*|\[project\]\s*)", "", title, flags=re.I).strip() or "note"
            slug = _slug(clean)
            path = mind / "projects" / ("%s.md" % slug)
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = "# %s\n\n%s\n" % (clean, body)
            if path.is_file():
                existing = _safe_read(path)
                # Avoid double-append when vault already persisted to same dir.
                try:
                    if body.strip() and body.strip() in (existing or ""):
                        pass
                    else:
                        path.write_text(existing.rstrip() + "\n\n---\n\n" + entry, encoding="utf-8")
                except Exception:
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
                try:
                    if body.strip() and body.strip() in (existing or ""):
                        pass
                    else:
                        path.write_text(existing.rstrip() + "\n\n" + entry, encoding="utf-8")
                except Exception:
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
    """Convenience for GET /whoami -> {ok, text, hits}. Always RAG-first."""
    return mind_recall("who am i")


__all__ = ["mind_recall", "mind_note", "who_am_i", "inject_context", "_cognee_remember"]
