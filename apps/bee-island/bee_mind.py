"""Bee mind vault helpers (stdlib only, offline, no Android)."""
import re

__all__ = [
    "who_am_i",
    "what_was_i_doing",
    "note",
    "inject_context",
    "classify_mind",
    "cache_read",
    "cache_write",
]

_ME_LIMIT = 400
_NOW_LIMIT = 400
_CONTEXT_LIMIT = 800
_TITLE_LIMIT = 120
_BODY_LIMIT = 2000

_GLOBAL_CACHE = {}

_SECRET_RES = (
    re.compile(r"authorization", re.IGNORECASE),
    re.compile(r"api[\s_\-]*keys?", re.IGNORECASE),
)


def _str(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return str(v)
    except Exception:
        return ""


def _has_secret(s):
    s = _str(s)
    for rx in _SECRET_RES:
        try:
            if rx.search(s):
                return True
        except Exception:
            continue
    return False


def _drop_secret_lines(text):
    s = _str(text)
    if not s:
        return ""
    kept = []
    for line in s.splitlines():
        bad = False
        for rx in _SECRET_RES:
            try:
                if rx.search(line):
                    bad = True
                    break
            except Exception:
                continue
        if not bad:
            kept.append(line)
    return "\n".join(kept)


def _cache_get(cache, names):
    if cache is None:
        return ""
    if isinstance(cache, str):
        return cache if cache.strip() else ""
    if isinstance(cache, dict):
        for n in names:
            try:
                if n in cache:
                    s = _str(cache.get(n))
                    if s.strip():
                        return s
            except Exception:
                continue
        return ""
    s = _str(cache)
    return s if s.strip() else ""


def _resolve(text, cache, names, kwargs, knit):
    s = _str(text)
    if s.strip():
        return s
    for k in knit:
        try:
            if k in kwargs and kwargs[k] is not None:
                cs = _str(kwargs[k])
                if cs.strip():
                    return cs
        except Exception:
            continue
    c = _cache_get(cache, names)
    if c.strip():
        return c
    return ""


def who_am_i(me_text=None, cache=None, *args, **kwargs):
    """First ~400 chars of ME.md-like text (Name: line if present)."""
    if cache is None:
        for a in args:
            if isinstance(a, dict):
                cache = a
                break
    raw = _resolve(
        me_text, cache,
        ["me", "ME", "me_text", "ME.md", "whoami", "who_am_i"],
        kwargs, ["fallback", "cached", "default", "me", "ME"],
    )
    if not raw.strip():
        return ""
    cleaned = _drop_secret_lines(raw).strip()
    if not cleaned:
        return ""
    name_line = None
    try:
        m = re.search(r"^\s*Name\s*:.*$", cleaned,
                      flags=re.MULTILINE | re.IGNORECASE)
        if m:
            name_line = m.group(0).strip()
    except Exception:
        name_line = None
    out = cleaned[:_ME_LIMIT] if len(cleaned) > _ME_LIMIT else cleaned
    if name_line and "name:" not in out.lower():
        room = _ME_LIMIT - len(name_line) - 1
        if room < 0:
            out = name_line[:_ME_LIMIT]
        else:
            out = name_line + "\n" + out[:room]
    if _has_secret(out):
        out = _drop_secret_lines(out).strip()[:_ME_LIMIT]
    return out


def what_was_i_doing(now_text=None, cache=None, *args, **kwargs):
    """NOW.md-like focus (clamped, secrets stripped)."""
    if cache is None:
        for a in args:
            if isinstance(a, dict):
                cache = a
                break
    raw = _resolve(
        now_text, cache,
        ["now", "NOW", "now_text", "NOW.md", "doing", "focus"],
        kwargs, ["fallback", "cached", "default", "now", "NOW"],
    )
    if not raw.strip():
        return ""
    cleaned = _drop_secret_lines(raw).strip()
    if not cleaned:
        return ""
    out = cleaned[:_NOW_LIMIT] if len(cleaned) > _NOW_LIMIT else cleaned
    if _has_secret(out):
        out = _drop_secret_lines(out).strip()[:_NOW_LIMIT]
    return out


def _clean_title(title):
    s = _str(title).replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if _has_secret(s):
        try:
            s = re.sub(r"authorization\S*", "", s, flags=re.IGNORECASE)
            s = re.sub(r"api[\s_\-]*keys?\S*", "", s, flags=re.IGNORECASE)
        except Exception:
            s = ""
        s = re.sub(r"\s+", " ", s).strip()
    if len(s) > _TITLE_LIMIT:
        s = s[:_TITLE_LIMIT].rstrip()
    buf = []
    for ch in s:
        o = ord(ch)
        if o == 127:
            continue
        if o < 32 and ch not in (" ", "\t"):
            continue
        buf.append(ch)
    return "".join(buf).strip()


def _clean_body(body):
    s = _str(body).strip()
    if not s:
        return ""
    s = _drop_secret_lines(s).strip()
    if len(s) > _BODY_LIMIT:
        s = s[:_BODY_LIMIT].rstrip()
    buf = []
    for ch in s:
        if ch in ("\n", "\t"):
            buf.append(ch)
            continue
        o = ord(ch)
        if o < 32 or o == 127:
            continue
        buf.append(ch)
    res = "".join(buf).strip()
    if _has_secret(res):
        res = _drop_secret_lines(res).strip()
        if len(res) > _BODY_LIMIT:
            res = res[:_BODY_LIMIT]
    return res


def note(title=None, body=None, *args, **kwargs):
    """Return {'title','body'} sanitized."""
    if isinstance(title, dict) and body is None and not args:
        try:
            body = title.get("body", "")
            title = title.get("title", "")
        except Exception:
            pass
    if body is None:
        for k in ("body", "text", "content", "note"):
            if k in kwargs and kwargs[k] is not None:
                body = kwargs[k]
                break
    if args:
        if body is None and len(args) >= 1:
            if isinstance(title, str) and title.strip():
                body = args[0]
            else:
                title = args[0]
                if len(args) > 1:
                    body = args[1]
        elif isinstance(title, str) and not title.strip():
            for a in args:
                if _str(a).strip():
                    title = a
                    break
    if (title is None or not _str(title).strip()) and "name" in kwargs:
        title = kwargs.get("name")
    return {"title": _clean_title(title), "body": _clean_body(body)}


def inject_context(me_text=None, now_text=None, cache=None,
                   *args, **kwargs):
    """Clamped ME+NOW concatenated, total <=800 chars, no secrets."""
    if cache is None:
        for a in args:
            if isinstance(a, dict):
                cache = a
                break
    for k in ("me", "ME", "me_text"):
        if me_text is None and k in kwargs and kwargs[k] is not None:
            me_text = kwargs[k]
    for k in ("now", "NOW", "now_text"):
        if now_text is None and k in kwargs and kwargs[k] is not None:
            now_text = kwargs[k]
    if cache is None:
        for k in ("cache", "store", "memory"):
            if k in kwargs and kwargs[k] is not None:
                cache = kwargs[k]
                break
    me_raw = _str(me_text)
    now_raw = _str(now_text)
    if not me_raw.strip() and isinstance(cache, dict):
        fb = _cache_get(cache, ["me", "ME", "me_text", "ME.md"])
        if fb.strip():
            me_raw = fb
    if not now_raw.strip() and isinstance(cache, dict):
        fb2 = _cache_get(cache, ["now", "NOW", "now_text", "NOW.md"])
        if fb2.strip():
            now_raw = fb2
    if not me_raw.strip() and not now_raw.strip():
        if isinstance(cache, str) and cache.strip():
            me_raw = cache
    me_part = _drop_secret_lines(me_raw).strip()
    now_part = _drop_secret_lines(now_raw).strip()
    me_part = me_part[:_ME_LIMIT] if len(me_part) > _ME_LIMIT else me_part
    now_part = now_part[:_NOW_LIMIT] if len(now_part) > _NOW_LIMIT else now_part
    if me_part and now_part:
        out = "ME:\n" + me_part + "\nNOW:\n" + now_part
    elif me_part:
        out = "ME:\n" + me_part
    elif now_part:
        out = "NOW:\n" + now_part
    else:
        return ""
    if len(out) > _CONTEXT_LIMIT:
        out = out[:_CONTEXT_LIMIT].rstrip()
    if _has_secret(out):
        out = _drop_secret_lines(out).strip()
        if len(out) > _CONTEXT_LIMIT:
            out = out[:_CONTEXT_LIMIT].rstrip()
    return out


def classify_mind(utterance=None, *args, **kwargs):
    """Classify mind intent: 'whoami' | 'now' | 'note' | None."""
    if utterance is None:
        for k in ("utterance", "text", "q", "query", "input"):
            if k in kwargs and kwargs[k] is not None:
                utterance = kwargs[k]
                break
        if utterance is None and args:
            utterance = args[0] if args else None
    s = _str(utterance)
    if not s.strip():
        return None
    low = s.lower()
    if re.search(r"\bwho\s+am\s+i\b", low):
        return "whoami"
    try:
        compact = re.sub(r"[\s_\-]+", "", low)
    except Exception:
        compact = low
    if "whoami" in compact:
        return "whoami"
    if re.search(r"\bwhat\s+was\s+i\s+doing\b", low):
        return "now"
    if re.search(r"\bwhat\s+am\s+i\s+doing\b", low):
        return "now"
    if re.search(r"\bremember\b", low):
        return "note"
    if re.search(r"^\s*note\b", low):
        return "note"
    return None


def cache_read(cache=None, key=None, default=None, *args, **kwargs):
    """Read from a plain-dict cache (no Android, no network)."""
    if key is None:
        for k in ("key", "name", "k"):
            if k in kwargs and kwargs[k] is not None:
                key = kwargs[k]
                break
    if default is None:
        for k in ("default", "fallback", "d"):
            if k in kwargs and kwargs[k] is not None:
                default = kwargs[k]
                break
    if args and key is not None and default is None:
        default = args[0]
    if isinstance(cache, str) and isinstance(key, dict):
        cache, key = key, cache
    if isinstance(cache, str) and key is None:
        key = cache
        cache = _GLOBAL_CACHE
    if cache is None and isinstance(key, str):
        cache = _GLOBAL_CACHE
    if not isinstance(cache, dict) or key is None:
        return default
    try:
        ks = str(key) if isinstance(key, (str, int)) else key
    except Exception:
        return default
    try:
        if ks in cache:
            return cache[ks]
    except Exception:
        pass
    try:
        if key in cache:
            return cache[key]
    except Exception:
        pass
    return default


def cache_write(cache=None, key=None, value=None, *args, **kwargs):
    """Write to a plain-dict cache (no Android, no network)."""
    if key is None:
        for k in ("key", "name", "k"):
            if k in kwargs and kwargs[k] is not None:
                key = kwargs[k]
                break
    if value is None:
        for k in ("value", "val", "v", "data"):
            if k in kwargs and kwargs[k] is not None:
                value = kwargs[k]
                break
    if args and key is not None and value is None:
        value = args[0]
    if isinstance(cache, str) and isinstance(key, dict):
        cache, key = key, cache
        if value is None and args:
            value = args[0]
    elif isinstance(cache, str):
        found = None
        for cand in (key, value) + tuple(args):
            if isinstance(cand, dict):
                found = cand
                break
        if found is not None:
            real_key = cache
            if isinstance(value, dict):
                real_val = key
                cache = value
                key = real_key
                value = real_val
            elif args and isinstance(args[-1], dict):
                cache = args[-1]
                key = real_key
                if value is None or isinstance(value, dict):
                    for v in (key, value) + tuple(args):
                        if v is not None and not isinstance(v, dict) \
                                and v != real_key:
                            value = v
                            break
                    key = real_key
    if isinstance(cache, str) and isinstance(key, str):
        is_dict_third = isinstance(value, dict) or any(
            isinstance(a, dict) for a in args)
        if not is_dict_third:
            value, key, cache = key, cache, _GLOBAL_CACHE
    if cache is None and key is not None:
        cache = _GLOBAL_CACHE
    if not isinstance(cache, dict) or key is None:
        return value
    try:
        ks = str(key) if isinstance(key, (str, int)) else key
    except Exception:
        return value
    try:
        cache[ks] = value
    except Exception:
        return value
    return value
