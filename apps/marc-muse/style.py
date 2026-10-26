"""Style card distiller (stdlib only).

- ``distill(messages, channel, person_slug)`` -> markdown style card with
  formality, emoji rate, avg length, greetings, signoff, Tamil/English mix,
  and examples of YOUR lines vs THEIR lines (both sides).
- ``write_card(channel, slug, markdown)`` persists to
  ``MARC_MIND_DIR/style/{channel}/{slug}.md`` via ``vault.upsert_style``
  when importable, else direct atomic file write.
- ``draft_like_me(person_slug, channel, intent)`` loads the card and returns
  a draft body string matching that channel (short WA, warmer IG, formal
  mail). Professional mail facts are never copied into IG/WA; ``policy.redact``
  is called when importable.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = [
    "distill",
    "write_card",
    "draft_like_me",
    "write_file",
    "mind_dir",
    "style_path",
    "load_card",
]

_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


# ---------------------------------------------------------------------------
# paths / atomic write
# ---------------------------------------------------------------------------

def mind_dir() -> Path:
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    raw = str(raw or "").strip() or "./var/mind"
    return Path(raw)


def _safe_slug(value: str, default: str = "untitled") -> str:
    cleaned = _SAFE_RE.sub("_", str(value or "").strip()).strip("_")
    if not cleaned:
        cleaned = default
    return cleaned[:120]


def _safe_channel(channel) -> str:
    if channel is None:
        return "general"
    if isinstance(channel, dict):
        for key in ("channel", "type", "source", "platform", "kind", "name", "id"):
            val = channel.get(key)
            if val:
                channel = val
                break
        else:
            channel = str(channel)
    s = str(channel or "").strip().lower() or "general"
    # keep short canonical names: whatsapp/wa, instagram/ig, gmail/mail
    return _safe_slug(s, "general")


def write_file(path, text: str) -> Path:
    """Atomically write *text* to *path* (mkdir -p + tmp + os.replace)."""
    target = Path(path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(text, str):
        text = str(text)
    tmp = parent / ("%s.%d.tmp" % (target.name, os.getpid()))
    counter = 0
    candidate = tmp
    while candidate.exists():
        counter += 1
        candidate = parent / ("%s.%d.%d.tmp" % (target.name, os.getpid(), counter))
    tmp = candidate
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass
    os.replace(tmp, target)
    return target


def style_path(channel, slug) -> Path:
    safe_ch = _safe_channel(channel)
    safe_slug = _safe_slug(slug, "untitled")
    return mind_dir() / "style" / safe_ch / ("%s.md" % safe_slug)


# ---------------------------------------------------------------------------
# vault / policy interop (importable-agnostic, stdlib only)
# ---------------------------------------------------------------------------

def _load_vault_fns():
    """Return (upsert_style_fn, read_md_fn) or (None, None)."""
    # 1) package-relative imports (works when loaded as a package)
    try:
        from .brain.vault import upsert_style as _up, read_md as _rd  # type: ignore
        return _up, _rd
    except Exception:
        pass
    try:
        from brain.vault import upsert_style as _up, read_md as _rd  # type: ignore
        return _up, _rd
    except Exception:
        pass
    # 2) file-location load (handles hyphenated dir apps/marc-muse)
    try:
        import importlib.util

        vault_file = Path(__file__).resolve().parent / "brain" / "vault.py"
        if vault_file.is_file():
            spec = importlib.util.spec_from_file_location("_marc_muse_vault", str(vault_file))
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                _up = getattr(mod, "upsert_style", None)
                _rd = getattr(mod, "read_md", None)
                if callable(_up) or callable(_rd):
                    return (_up if callable(_up) else None,
                            _rd if callable(_rd) else None)
    except Exception:
        pass
    return None, None


def _load_redact_fn():
    """Return policy.redact callable or None."""
    try:
        from .policy import redact as _re  # type: ignore
        if callable(_re):
            return _re
    except Exception:
        pass
    try:
        from policy import redact as _re  # type: ignore
        if callable(_re):
            return _re
    except Exception:
        pass
    try:
        import importlib.util

        pol_file = Path(__file__).resolve().parent / "policy.py"
        if pol_file.is_file():
            spec = importlib.util.spec_from_file_location("_marc_muse_policy", str(pol_file))
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                fn = getattr(mod, "redact", None)
                if callable(fn):
                    return fn
    except Exception:
        pass
    return None


def _fallback_redact(text: str) -> str:
    s = "" if text is None else str(text)
    if not s:
        return s
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
               "[redacted-email]", s)
    s = re.sub(r"\+?\d[\d\s\-().]{6,}\d", "[redacted-phone]", s)
    return s


def _redact_for_dest(text: str, dest_channel) -> str:
    """Redact professional identifiers when dest is IG/WA (non-mail)."""
    s = "" if text is None else str(text)
    c = str(dest_channel or "").strip().lower()
    is_mail = ("mail" in c or "gmail" in c or "email" in c
               or "professional" in c or "work" in c or "outlook" in c)
    if is_mail:
        return s
    # IG / WA / general destinations: redact professional facts.
    fn = _load_redact_fn()
    if fn is not None:
        try:
            # Deny work_ok so mail facts never leak to IG/WA.
            return str(fn(s, {"work_ok": False}, dest_channel))
        except Exception:
            pass
    return _fallback_redact(s)


def write_card(channel, slug, markdown) -> Path:
    """Persist *markdown* to ``style/{channel}/{slug}.md``. Returns path."""
    text = markdown if isinstance(markdown, str) else str(markdown)
    if not text.endswith("\n"):
        text += "\n"
    safe_ch = _safe_channel(channel)
    safe_slug = _safe_slug(slug, "untitled")
    up_fn, _ = _load_vault_fns()
    if up_fn is not None:
        try:
            return Path(up_fn(safe_ch, safe_slug, text))
        except Exception:
            pass
    target = style_path(safe_ch, safe_slug)
    return write_file(target, text)


def load_card(person_slug, channel) -> str:
    """Load style card markdown for (channel, slug); "" if missing."""
    safe_ch = _safe_channel(channel)
    safe_slug = _safe_slug(person_slug, "untitled")
    _, read_fn = _load_vault_fns()
    if read_fn is not None:
        try:
            text = read_fn("style/%s/%s.md" % (safe_ch, safe_slug))
            if isinstance(text, str) and text.strip():
                return text
        except Exception:
            pass
    # Also try alternate channel spellings before giving up.
    try:
        p = style_path(safe_ch, safe_slug)
        if p.is_file():
            return p.read_text(encoding="utf-8")
    except Exception:
        return ""
    return ""


# ---------------------------------------------------------------------------
# message helpers
# ---------------------------------------------------------------------------

_TEXT_KEYS = ("text", "body", "message", "content", "line", "utterance", "msg")
_SENDER_KEYS = ("from", "sender", "author", "speaker", "role", "side", "who",
                "name", "slug", "by", "source")


def _extract_text(msg) -> str:
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, (int, float)):
        return str(msg)
    if isinstance(msg, dict):
        for k in _TEXT_KEYS:
            v = msg.get(k)
            if isinstance(v, str) and v.strip():
                return v
            if v not in (None, "") and k in ("text", "body", "message", "content"):
                return str(v)
        # fallback: first non-sender string value
        for k, v in msg.items():
            if k.lower() in _SENDER_KEYS + ("mine", "is_mine", "ismine",
                                            "from_me", "fromme", "channel"):
                continue
            if isinstance(v, str) and v.strip():
                return v
        return ""
    return str(msg)


def _extract_sender(msg) -> str:
    if not isinstance(msg, dict):
        return ""
    for k in _SENDER_KEYS:
        if msg.get(k) not in (None, ""):
            return str(msg[k])
    return ""


_MINE_TOKENS = {"me", "mine", "self", "you", "your", "yours", "ranjith",
                "marc", "owner", "human", "i", "myself", "personal"}
_THEIRS_TOKENS = {"them", "their", "theirs", "they", "contact", "friend",
                  "other", "peer", "stranger", "user"}


def _is_mine(msg, person_slug: str):
    """True=YOUR line, False=THEIR line, None=unknown."""
    if isinstance(msg, dict):
        for k in ("mine", "is_mine", "isMine", "from_me", "fromMe", "fromme",
                  "is_self", "isSelf", "own"):
            if k in msg:
                v = msg[k]
                if isinstance(v, bool):
                    return v
                s = str(v).strip().lower()
                if s in ("1", "true", "yes", "y", "mine", "me", "self", "own"):
                    return True
                if s in ("0", "false", "no", "n", "theirs", "them", "other"):
                    return False
        role = str(msg.get("role", "") or "").strip().lower()
        if role in ("me", "self", "user", "human", "assistant", "ranjith", "marc"):
            # "user" in chat dumps usually means the owner side.
            return True
        if role in ("contact", "friend", "stranger", "peer", "other", "them",
                    "theirs", "assistant_other"):
            return False
        side = str(msg.get("side", "") or "").strip().lower()
        if side in _MINE_TOKENS:
            return True
        if side in _THEIRS_TOKENS:
            return False
    sender = _extract_sender(msg).strip()
    sl = sender.lower().lstrip("@")
    want = str(person_slug or "").strip().lower().lstrip("@")
    if sl:
        if sl in _MINE_TOKENS:
            return True
        if sl in _THEIRS_TOKENS:
            return False
        if want and (sl == want or sl.replace("_", " ") == want
                     or want in sl or sl in want):
            return False
        # explicit "me: ..." prefixes handled by caller; sender names that
        # look like the owner are YOUR.
        if sl in ("ranjith", "marc", "me", "myself"):
            return True
    return None


def _split_sides(messages, person_slug: str):
    mine: list[str] = []
    theirs: list[str] = []
    msgs = list(messages or [])
    unknowns: list[tuple[int, str]] = []
    for idx, m in enumerate(msgs):
        text = _extract_text(m).strip()
        if not text:
            continue
        flag = _is_mine(m, person_slug)
        if flag is True:
            mine.append(text)
        elif flag is False:
            theirs.append(text)
        else:
            unknowns.append((idx, text))
    if unknowns:
        if not mine and not theirs:
            # No signals at all: alternate so both sides get examples.
            for idx, text in unknowns:
                if len(mine) <= len(theirs):
                    mine.append(text)
                else:
                    theirs.append(text)
        elif not mine:
            # All explicit were THEIR: give half of unknowns to YOUR.
            half = max(1, (len(unknowns) + 1) // 2)
            mine.extend(t for _, t in unknowns[:half])
            theirs.extend(t for _, t in unknowns[half:])
            if not mine and unknowns:
                mine.append(unknowns[0][1])
        elif not theirs:
            half = max(1, (len(unknowns) + 1) // 2)
            theirs.extend(t for _, t in unknowns[:half])
            mine.extend(t for _, t in unknowns[half:])
            if not theirs and unknowns:
                theirs.append(unknowns[0][1])
        else:
            # Both sides present: unknowns are likely THEIR (incoming).
            theirs.extend(t for _, t in unknowns)
    return mine, theirs


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),
    (0x1F000, 0x1F2FF),
    (0x2190, 0x21FF),
)

_EMOTICON_RE = re.compile(r"(?::|;|=|8)[\-o']?[\)\]\(DdpP3/\\|]+|<3")


def _count_emoji(text: str) -> int:
    n = 0
    for ch in str(text or ""):
        o = ord(ch)
        if o == 0x200D or o == 0xFE0F:
            continue
        for lo, hi in _EMOJI_RANGES:
            if lo <= o <= hi:
                n += 1
                break
    try:
        n += len(_EMOTICON_RE.findall(str(text or "")))
    except Exception:
        pass
    return n


_GREETINGS = [
    "vanakkam", "good morning", "good afternoon", "good evening",
    "hello", "hey", "hi", "dear", "yo", "machi", "bro", "anna",
    "akka", "sir", "madam", "respected",
]

_SIGNOFFS = [
    "thanks & regards", "best regards", "kind regards", "warm regards",
    "thank you", "thanks", "nandri", "regards", "best", "cheers",
    "take care", "bye", "see you", "seri", "paakalam", "ok da",
    "sincerely",
]

_TAMIL_WORDS = {
    "vanakkam", "nandri", "seri", "illa", "aama", "aamam", "da", "di",
    "machi", "mapla", "anna", "akka", "thangachi", "annan", "ennada",
    "epdi", "eppadi", "nalla", "romba", "konjam", "illa", "aama",
    "saptiya", "saapteengala", "paakalam", "varen", "pokalam", "sari",
}

_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")


def _word_list(text: str) -> list[str]:
    return re.findall(r"[A-Za-z\u0B80-\u0BFF']+", str(text or ""))


def _detect_greetings(lines: list[str]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for line in lines:
        s = str(line or "").strip().lower()
        if not s:
            continue
        head = s[:40]
        for g in _GREETINGS:
            if head.startswith(g) or (" " + g + " ") in (" " + head + " "):
                counts[g] = counts.get(g, 0) + 1
                break
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _detect_signoffs(lines: list[str]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for line in lines:
        s = str(line or "").strip().lower().rstrip("!., ")
        if not s:
            continue
        tail = s[-40:]
        for g in _SIGNOFFS:
            if tail.endswith(g) or g in tail:
                counts[g] = counts.get(g, 0) + 1
                break
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _formality(lines: list[str]) -> tuple[str, float]:
    """Return (label, score 0..1 where 1 = formal)."""
    if not lines:
        return "mixed", 0.5
    formal_hits = 0
    informal_hits = 0
    total = 0
    for line in lines:
        s = str(line or "")
        if not s.strip():
            continue
        total += 1
        low = s.strip().lower()
        if re.match(r"^(dear\s|respected\s|hello\s+sir|hello\s+madam|good\s+(morning|afternoon|evening)\b)", low):
            formal_hits += 2
        if re.search(r"\b(dear|sir|madam|respected|kindly|please|thank\s+you|thanks\s+&\s+regards|best\s+regards|sincerely|regards)\b", low):
            formal_hits += 1
        if re.search(r"\b(would\s+you|could\s+you|may\s+i|requesting|confirm|meeting|schedule|attached|invoice|regarding)\b", low):
            formal_hits += 1
        if s.strip() and s.strip()[0].isupper() and re.search(r"[.!?]\s*$", s.strip()):
            formal_hits += 1
        # informal signals
        if _count_emoji(s) > 0:
            informal_hits += 1
        if re.search(r"\b(lol|haha|hehe|lmao|omg|gonna|wanna|yeah|yep|nope|bro|machi|da\b|dude|yo)\b", low):
            informal_hits += 1
        if re.search(r"[!?]{2,}", s):
            informal_hits += 1
        if s.strip() and s.strip() == s.strip().lower() and len(s.strip()) > 3:
            informal_hits += 1
        if re.search(r"\b(don't|can't|won't|i'm|you're|it's|that's)\b", low):
            informal_hits += 1
    if total == 0:
        return "mixed", 0.5
    score = 0.5 + 0.12 * formal_hits - 0.12 * informal_hits
    score = max(0.0, min(1.0, round(score, 2)))
    if score >= 0.65:
        label = "formal"
    elif score <= 0.35:
        label = "casual"
    else:
        label = "mixed"
    return label, score


def _avg_len(lines: list[str]) -> tuple[float, float]:
    if not lines:
        return 0.0, 0.0
    chars = [len(s) for s in lines]
    words = [len(_word_list(s)) for s in lines]
    return round(sum(chars) / len(chars), 1), round(sum(words) / len(words), 1)


def _tamil_english(lines: list[str]) -> dict:
    n = len(lines) if lines else 1
    tamil_script = 0
    tamil_word = 0
    english = 0
    mixed = 0
    for line in lines:
        s = str(line or "")
        has_script = bool(_TAMIL_RE.search(s))
        toks = [t.lower() for t in _word_list(s)]
        has_tword = any(t in _TAMIL_WORDS for t in toks)
        has_eng = bool(re.search(r"[A-Za-z]{2,}", s))
        has_tamil = has_script or has_tword
        if has_tamil:
            if has_script:
                tamil_script += 1
            else:
                tamil_word += 1
        if has_eng:
            english += 1
        if has_tamil and has_eng:
            mixed += 1
    denom = max(1, len(lines))
    return {
        "tamil_script_pct": round(100.0 * tamil_script / denom, 1),
        "tamil_any_pct": round(100.0 * (tamil_script + tamil_word) / denom, 1),
        "english_pct": round(100.0 * english / denom, 1),
        "mixed_pct": round(100.0 * mixed / denom, 1),
        "n": len(lines),
    }


def _shorten(s: str, limit: int = 200) -> str:
    one = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(one) <= limit:
        return one
    return one[: max(0, limit - 1)].rstrip() + "…"


# ---------------------------------------------------------------------------
# distill
# ---------------------------------------------------------------------------

def distill(messages, channel="", person_slug="") -> str:
    """Distill *messages* into a markdown style card for (channel, slug)."""
    ch = _safe_channel(channel)
    slug = _safe_slug(person_slug, "untitled")
    msgs = list(messages or [])
    mine, theirs = _split_sides(msgs, slug)

    # Stats focus on YOUR voice; fall back to all lines when YOUR is empty.
    voice = mine if mine else ([_extract_text(m).strip() for m in msgs
                                if _extract_text(m).strip()])
    label, score = _formality(voice)
    total_emoji = sum(_count_emoji(t) for t in voice)
    n_voice = max(1, len(voice))
    emoji_per_msg = round(total_emoji / n_voice, 2)
    total_chars = sum(len(t) for t in voice)
    emoji_per_100 = round(100.0 * total_emoji / max(1, total_chars), 2)
    avg_chars, avg_words = _avg_len(voice)
    greetings = _detect_greetings(voice)
    signoffs = _detect_signoffs(voice)
    mix = _tamil_english(voice)

    if greetings:
        greet_str = ", ".join("%s (%d)" % (g, c) for g, c in greetings[:3])
    else:
        greet_str = "none observed"
    if signoffs:
        sign_str = ", ".join("%s (%d)" % (g, c) for g, c in signoffs[:3])
    else:
        sign_str = "none observed"

    if mix["tamil_script_pct"] > 0:
        lang_line = ("Tamil script %.1f%%, any Tamil %.1f%%, English %.1f%%, "
                     "mixed Tamil+English %.1f%% (n=%d)"
                     % (mix["tamil_script_pct"], mix["tamil_any_pct"],
                        mix["english_pct"], mix["mixed_pct"], mix["n"]))
    elif mix["tamil_any_pct"] > 0:
        lang_line = ("No Tamil script, but transliterated Tamil in %.1f%% of lines; "
                     "English %.1f%%, mixed %.1f%% (n=%d)"
                     % (mix["tamil_any_pct"], mix["english_pct"],
                        mix["mixed_pct"], mix["n"]))
    else:
        lang_line = ("English-only (no Tamil script or Tamil words observed); "
                     "English %.1f%% (n=%d)" % (mix["english_pct"], mix["n"]))

    # Tone hint for draft_like_me.
    if label == "formal":
        tone = "formal, polite, full sentences"
    elif label == "casual":
        tone = "casual, warm, short lines"
    else:
        tone = "balanced, friendly-direct"

    lines: list[str] = []
    lines.append("# Style: %s/%s" % (ch, slug))
    lines.append("")
    lines.append("- Channel: %s" % ch)
    lines.append("- Person: %s" % slug)
    lines.append("- Tone: %s" % tone)
    lines.append("- Voice lines: %d (YOUR=%d, THEIR=%d)" % (len(voice), len(mine), len(theirs)))
    lines.append("")
    lines.append("## Formality")
    lines.append("")
    lines.append("Formality: %s (score %.2f; 1.0 = formal, 0.0 = casual)." % (label, score))
    lines.append("")
    lines.append("## Emoji rate")
    lines.append("")
    lines.append("Emoji rate: %.2f emojis/message (%d emojis across %d YOUR lines; %.2f per 100 chars)."
                 % (emoji_per_msg, total_emoji, len(voice), emoji_per_100))
    lines.append("")
    lines.append("## Avg length")
    lines.append("")
    lines.append("Avg length: %.1f chars (%.1f words) across %d YOUR lines."
                 % (avg_chars, avg_words, len(voice)))
    lines.append("")
    lines.append("## Greetings")
    lines.append("")
    lines.append("Greetings: %s." % greet_str)
    lines.append("")
    lines.append("## Signoff")
    lines.append("")
    lines.append("Signoff: %s." % sign_str)
    lines.append("")
    lines.append("## Tamil/English mix")
    lines.append("")
    lines.append("Tamil/English mix: %s" % lang_line)
    lines.append("")
    lines.append("## Examples — YOUR lines")
    lines.append("")
    if mine:
        for ex in mine[:3]:
            lines.append("- YOUR: %s" % _shorten(ex))
    else:
        lines.append("- YOUR: (no YOUR lines observed)")
    lines.append("")
    lines.append("## Examples — THEIR lines")
    lines.append("")
    if theirs:
        for ex in theirs[:3]:
            lines.append("- THEIR: %s" % _shorten(ex))
    else:
        lines.append("- THEIR: (no THEIR lines observed)")
    lines.append("")
    lines.append("## Do / Don't")
    lines.append("")
    if ch in ("whatsapp", "wa", "mixed"):
        lines.append("- Do: keep it short (1-2 lines), match greeting, Tamil/English as above.")
        lines.append("- Don't: paste formal mail facts, long paragraphs, or work emails/phones.")
    elif ch in ("instagram", "ig", "igdm", "ig_dm", "insta"):
        lines.append("- Do: stay warm and friendly, one short paragraph, light emoji ok.")
        lines.append("- Don't: paste formal mail facts, work emails/phones, or long letters.")
    else:
        lines.append("- Do: stay formal and polite, full sentences, clear signoff.")
        lines.append("- Don't: use slang, heavy emoji, or casual one-liners.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# draft_like_me
# ---------------------------------------------------------------------------

def _card_hint(card: str, section: str) -> str:
    """Extract the first meaningful phrase from a card *section*."""
    if not card or not section:
        return ""
    try:
        # Find "## <section>" then grab following non-empty lines.
        pat = re.compile(r"^##\s*%s\s*$" % re.escape(section), re.M | re.I)
        mt = pat.search(card)
        if not mt:
            # loose contains match
            pat2 = re.compile(r"^##.*%s.*$" % re.escape(section), re.M | re.I)
            mt = pat2.search(card)
        if not mt:
            return ""
        tail = card[mt.end():]
        # stop at next ## heading
        nxt = re.search(r"^##\s+", tail, re.M)
        block = tail[: nxt.start()] if nxt else tail[:600]
        for line in block.splitlines():
            s = line.strip().strip("-* ").strip()
            if not s:
                continue
            low = s.lower()
            if low.startswith(("greetings:", "signoff:", "formality:",
                               "emoji rate:", "avg length:", "tamil/english mix:",
                               "tone:", "channel:", "person:")):
                _, _, val = s.partition(":")
                val = val.strip().rstrip(".")
                if val and val.lower() != "none observed":
                    # "hi (2), hello (1)" -> "hi"
                    first = re.split(r"[,(;]", val)[0].strip().strip("\"'")
                    return first
                return ""
            return s[:80]
    except Exception:
        return ""
    return ""


def _canon_channel(channel) -> str:
    c = str(channel or "").strip().lower()
    if "whatsapp" in c or c == "wa" or re.search(r"(^|[\W_])wa($|[\W_])", c):
        return "whatsapp"
    if "instagram" in c or c in ("ig", "insta", "igdm", "ig_dm") or re.search(r"(^|[\W_])ig($|[\W_])", c):
        return "instagram"
    if ("mail" in c or "gmail" in c or "email" in c or "professional" in c
            or "work" in c or "outlook" in c):
        return "mail"
    return c or "general"


def draft_like_me(person_slug, channel, intent="") -> str:
    """Return a draft body string in the card's voice for *channel*.

    - WhatsApp: short (1-2 lines).
    - Instagram: warmer, friendly.
    - Mail: formal with greeting + signoff.
    Professional mail facts in *intent* are redacted for IG/WA.
    """
    slug = _safe_slug(person_slug, "untitled")
    canon = _canon_channel(channel)
    raw_intent = "" if intent is None else str(intent).strip()
    if not raw_intent:
        raw_intent = "[intent]"

    # Never leak professional mail facts into IG/WA drafts.
    if canon in ("whatsapp", "instagram"):
        clean = _redact_for_dest(raw_intent, channel)
    else:
        clean = raw_intent
    clean_one = re.sub(r"\s+", " ", clean).strip()

    card = ""
    try:
        card = load_card(slug, channel) or ""
        if not card:
            # try canonical channel name too
            card = load_card(slug, canon) or ""
    except Exception:
        card = ""

    greet = _card_hint(card, "Greetings").strip()
    sign = _card_hint(card, "Signoff").strip()
    if greet.lower() in ("none observed", "none", ""):
        greet = ""
    if sign.lower() in ("none observed", "none", ""):
        sign = ""
    # Strip counts like "hi (2)".
    greet = re.sub(r"\s*\(\d+\)\s*$", "", greet).strip()
    sign = re.sub(r"\s*\(\d+\)\s*$", "", sign).strip()

    name = slug.replace("_", " ").strip().title() if slug else "there"

    if canon == "whatsapp":
        g = greet.capitalize() if greet else "Hi"
        # Short WA: greeting + intent, hard cap.
        body = "%s! %s" % (g, clean_one)
        if len(body) > 220:
            body = body[:219].rstrip() + "…"
        return body
    if canon == "instagram":
        g = greet.capitalize() if greet else "Heyy"
        # Warmer IG: friendly opener + intent + light warmth.
        core = clean_one
        if len(core) > 280:
            core = core[:279].rstrip() + "…"
        # Keep any emoji the user put in intent; add one warm touch.
        touch = " 😊" if "😊" not in core and "✨" not in core else ""
        return "%s! %s%s" % (g, core, touch)
    # Formal mail.
    if greet and greet.lower() not in ("hi", "hey", "heyy", "yo"):
        salutation = greet.capitalize()
    else:
        salutation = "Dear %s" % name if name and name.lower() != "there" else "Hello"
    if "dear" in salutation.lower() or "hello" in salutation.lower() \
            or "good " in salutation.lower() or "vanakkam" in salutation.lower():
        open_line = "%s," % salutation.rstrip(",")
    else:
        open_line = "%s," % salutation
    if sign and len(sign) < 60:
        close = sign.capitalize() if sign.lower() not in ("best", "regards") else "Best regards"
    else:
        close = "Best regards"
    return "%s\n\n%s\n\n%s,\nRanjith" % (open_line, clean_one, close)


if __name__ == "__main__":
    _msgs = [
        {"from": "me", "text": "Hi Priya! Saptiya? 😊"},
        {"from": "priya", "text": "Hi! Aama, neenga?"},
        {"from": "me", "text": "Good morning! Please confirm the plan. Thank you."},
    ]
    _card = distill(_msgs, "whatsapp", "priya")
    assert "Formality" in _card and "Emoji rate" in _card
    assert "Avg length" in _card and "Greetings" in _card
    assert "Signoff" in _card and "Tamil" in _card and "English" in _card
    assert "YOUR" in _card and "THEIR" in _card
    _wa = draft_like_me("priya", "whatsapp", "meeting at 5pm")
    assert len(_wa) <= 240, _wa
    _leak = draft_like_me("sam", "instagram", "mail me at sam@work.com")
    assert "sam@work.com" not in _leak, _leak
    print("style self-check ok")
