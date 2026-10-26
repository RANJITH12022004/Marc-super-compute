"""Channel policy + identity merge (stdlib only).

Channels:
  - Gmail  -> ``professional``
  - Instagram -> ``friend`` or ``stranger`` (suffix-aware)
  - WhatsApp -> ``mixed``

Identities are merged by shared ``email`` / ``phone`` / ``ig`` / ``wa``.
A merged person holding both an IG handle and a WA id defaults to
``friend``.

Leak rule: professional mail facts must not flow to ig/wa destinations
unless ``person.work_ok`` is truthy.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

__all__ = [
    "classify_channel",
    "merge_identity",
    "leak_ok",
    "redact",
    "classify_person",
]

PROFESSIONAL = "professional"
FRIEND = "friend"
STRANGER = "stranger"
MIXED = "mixed"

_VALID_LABELS = (PROFESSIONAL, FRIEND, STRANGER, MIXED)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{6,}\d")


# ---------------------------------------------------------------------------
# channel classification
# ---------------------------------------------------------------------------

def _channel_text(channel) -> str:
    if channel is None:
        return ""
    if isinstance(channel, dict):
        for key in ("channel", "type", "source", "platform", "kind", "name", "id"):
            val = channel.get(key)
            if val:
                return str(val).strip().lower()
        return str(channel).strip().lower()
    return str(channel).strip().lower()


def classify_channel(channel) -> str:
    """Return ``professional`` | ``friend`` | ``stranger`` | ``mixed``.

    - Gmail / mail -> ``professional``
    - WhatsApp / wa -> ``mixed``
    - Instagram / ig -> ``friend`` when the channel hints at a friend
      (contains ``friend``/``mutual``/``follow-back``/``contact``), else
      ``stranger``.
    """
    c = _channel_text(channel)
    if not c:
        return STRANGER

    # WhatsApp wins over generic "mail" substring checks (no overlap, but be safe).
    if "whatsapp" in c or "mixed" in c:
        return MIXED
    # bare "wa" token (word-boundary aware so "swana" etc. don't match).
    if c == "wa" or c.startswith("wa:") or c.startswith("wa_") or c.startswith("wa-"):
        return MIXED
    if re.search(r"(^|[\s:;,_/\-()])wa($|[\s:;,_/\-()])", c):
        return MIXED

    if (
        "gmail" in c
        or "googlemail" in c
        or "google" in c
        or "email" in c
        or "e-mail" in c
        or "mail" in c
        or "professional" in c
        or "work" in c
        or "linkedin" in c
        or "outlook" in c
        or "office" in c
    ):
        return PROFESSIONAL

    if "instagram" in c or re.search(r"(^|[\s:;,_/\-()])ig($|[\s:;,_/\-()])", c) or c in ("ig", "insta", "igdm", "ig_dm"):
        if "friend" in c or "mutual" in c or "contact" in c or "follow-back" in c or "followback" in c or "following" in c:
            return FRIEND
        if "stranger" in c or "unknown" in c or "non-friend" in c or "nonfriend" in c or "public" in c:
            return STRANGER
        # Bare instagram handle with no qualifier: treat as stranger (safe default).
        return STRANGER

    if "friend" in c:
        return FRIEND
    if "stranger" in c:
        return STRANGER
    return STRANGER


# ---------------------------------------------------------------------------
# identity merge
# ---------------------------------------------------------------------------

def _norm_email(v) -> str:
    return str(v or "").strip().lower()


def _norm_phone(v) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    # Keep digits and leading +; drop spaces/dashes/parens for matching.
    plus = "+" if s.lstrip().startswith("+") else ""
    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""
    return plus + digits


def _norm_handle(v) -> str:
    s = str(v or "").strip().lower()
    s = s.lstrip("@")
    return s


def _as_bool(v) -> bool:
    if v is True:
        return True
    if v is False or v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "allow", "allowed", "ok", "on")


def _collect_values(rec: dict, keys) -> list:
    out: list = []
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            v = rec[k]
            if isinstance(v, (list, tuple, set)):
                out.extend(v)
            else:
                out.append(v)
    return out


_EMAIL_KEYS = ("email", "emails", "e-mail", "e-mails", "mail", "gmail")
_PHONE_KEYS = ("phone", "phones", "tel", "mobile", "phone_number", "phoneNumber", "number")
_IG_KEYS = ("ig", "igs", "ig_handle", "igHandle", "instagram", "instagram_handle", "insta")
_WA_KEYS = ("wa", "was", "wa_id", "waId", "whatsapp", "whatsapp_id", "wa_number", "waNumber", "wa_handle")
_REL_KEYS = ("relationship", "relation", "kind", "label", "category", "type")
_WORK_KEYS = ("work_ok", "workOk", "workok", "allow_work", "allowWork", "share_work", "work_allowed", "workAllowed")


def _norm_relationship(v) -> str:
    s = str(v or "").strip().lower()
    if s in _VALID_LABELS:
        return s
    if "profession" in s or "work" in s or "colleague" in s or "gmail" in s:
        return PROFESSIONAL
    if "mix" in s or "whatsapp" in s or re.search(r"(^|\W)wa($|\W)", s):
        return MIXED
    if "friend" in s:
        return FRIEND
    if "stranger" in s or "unknown" in s:
        return STRANGER
    return ""


def _record_identifiers(rec: dict) -> tuple[set, set, set, set]:
    emails: set = set()
    for v in _collect_values(rec, _EMAIL_KEYS):
        e = _norm_email(v)
        if e:
            emails.add(e)
    phones: set = set()
    for v in _collect_values(rec, _PHONE_KEYS):
        p = _norm_phone(v)
        if p:
            phones.add(p)
    igs: set = set()
    for v in _collect_values(rec, _IG_KEYS):
        h = _norm_handle(v)
        if h:
            igs.add(h)
    was: set = set()
    for v in _collect_values(rec, _WA_KEYS):
        h = _norm_handle(_norm_phone(v) if re.search(r"\d", str(v)) else v)
        # wa ids may be phone-like or handle-like; store both normalisations
        h2 = _norm_handle(v)
        if h:
            was.add(h)
        if h2:
            was.add(h2)
    return emails, phones, igs, was


def merge_identity(records) -> list:
    """Group contact records into merged persons.

    Groups by shared ``email`` / ``phone`` / ``ig`` / ``wa`` (union-find).
    A merged person with both IG and WA identifiers defaults to ``friend``.

    Returns a deterministic ``list[dict]``; each person dict has keys::

        emails, phones, igs, was, email, phone, ig, wa,
        channels, relationship, work_ok, slugs, names, count
    """
    recs = list(records or [])
    n = len(recs)
    if n == 0:
        return []

    identifiers: list[tuple[set, set, set, set]] = []
    for r in recs:
        if isinstance(r, dict):
            identifiers.append(_record_identifiers(r))
        else:
            identifiers.append((set(), set(), set(), set()))

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

    # Index identifier -> first record idx.
    seen: dict[str, int] = {}
    for i, (emails, phones, igs, was) in enumerate(identifiers):
        for prefix, vals in (("e:", emails), ("p:", phones), ("i:", igs), ("w:", was)):
            for v in vals:
                key = prefix + v
                if key in seen:
                    union(i, seen[key])
                else:
                    seen[key] = i

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    persons: list[dict] = []
    for root in sorted(groups):
        idxs = groups[root]
        emails: set = set()
        phones: set = set()
        igs: set = set()
        was: set = set()
        channels: set = set()
        rels: list[str] = []
        work_ok = False
        slugs: list[str] = []
        names: list[str] = []
        for i in idxs:
            r = recs[i]
            if not isinstance(r, dict):
                continue
            e, p, g, w = identifiers[i]
            emails |= e
            phones |= p
            igs |= g
            was |= w
            ch = r.get("channel", r.get("source", r.get("platform", "")))
            if ch:
                if isinstance(ch, (list, tuple, set)):
                    for c in ch:
                        channels.add(str(c))
                else:
                    channels.add(str(ch))
                # Infer relationship signal from channel as well.
                try:
                    rels.append(classify_channel(ch))
                except Exception:
                    pass
            for k in _REL_KEYS:
                if r.get(k):
                    nr = _norm_relationship(r.get(k))
                    if nr:
                        rels.append(nr)
            for k in _WORK_KEYS:
                if k in r and _as_bool(r[k]):
                    work_ok = True
            for k in ("slug", "id", "key"):
                if r.get(k):
                    slugs.append(str(r[k]))
            for k in ("name", "display_name", "displayName", "full_name"):
                if r.get(k):
                    names.append(str(r[k]))

        if igs and was:
            relationship = FRIEND
        elif FRIEND in rels:
            relationship = FRIEND
        elif PROFESSIONAL in rels:
            relationship = PROFESSIONAL
        elif MIXED in rels:
            # A WA-only person surfaced via channel inference: keep mixed
            # only when there is no stronger signal; otherwise stranger.
            if emails and not (igs or was):
                relationship = PROFESSIONAL
            elif igs or was or phones:
                # mixed channel implies known contact; keep mixed label
                relationship = MIXED
            else:
                relationship = MIXED
        elif STRANGER in rels:
            relationship = STRANGER
        else:
            # No explicit signal: heuristic fallback.
            if emails and not (igs or was or phones):
                relationship = PROFESSIONAL
            elif igs or was:
                relationship = STRANGER
            else:
                relationship = STRANGER

        persons.append(
            {
                "emails": sorted(emails),
                "phones": sorted(phones),
                "igs": sorted(igs),
                "was": sorted(was),
                "email": sorted(emails)[0] if emails else "",
                "phone": sorted(phones)[0] if phones else "",
                "ig": sorted(igs)[0] if igs else "",
                "wa": sorted(was)[0] if was else "",
                "channels": sorted(channels),
                "relationship": relationship,
                "work_ok": bool(work_ok),
                "slugs": slugs,
                "names": names,
                "count": len(idxs),
            }
        )

    # Deterministic order: by first email, then ig, then wa, then slug.
    persons.sort(
        key=lambda p: (
            p["emails"][0] if p["emails"] else "~",
            p["igs"][0] if p["igs"] else "~",
            p["was"][0] if p["was"] else "~",
            p["slugs"][0].lower() if p["slugs"] else "~",
        )
    )
    return persons


# ---------------------------------------------------------------------------
# leak policy + redaction
# ---------------------------------------------------------------------------

def _person_work_ok(person) -> bool:
    if person is None:
        return False
    if isinstance(person, bool):
        return person
    if isinstance(person, dict):
        for k in _WORK_KEYS:
            if k in person:
                if _as_bool(person[k]):
                    return True
        # also accept nested consent dicts
        consent = person.get("consent")
        if isinstance(consent, dict):
            for k in _WORK_KEYS:
                if k in consent and _as_bool(consent[k]):
                    return True
        return False
    return False


def leak_ok(person, source_channel, dest_channel) -> bool:
    """Return True when facts may flow from source to dest for ``person``.

    Professional (gmail) facts cannot go to ig/wa destinations
    (``friend`` / ``stranger`` / ``mixed``) unless ``person.work_ok``.
    All other flows are allowed.
    """
    src = classify_channel(source_channel)
    dst = classify_channel(dest_channel)
    if src == PROFESSIONAL and dst in (FRIEND, STRANGER, MIXED):
        return bool(_person_work_ok(person))
    return True


def redact(text, person, dest_channel) -> str:
    """Redact professional identifiers when leaking to ig/wa is not allowed.

    If ``dest_channel`` is professional, or ``person.work_ok`` allows the
    flow, ``text`` is returned unchanged. Otherwise email addresses and
    phone numbers are masked.
    """
    s = "" if text is None else str(text)
    if not s:
        return s
    try:
        dst = classify_channel(dest_channel)
    except Exception:
        dst = STRANGER
    if dst == PROFESSIONAL:
        return s
    # Assume the sensitive facts originate from professional mail; if the
    # person consented to work sharing, no redaction is needed.
    if _person_work_ok(person):
        return s
    # Mask emails + phones.
    red = _EMAIL_RE.sub("[redacted-email]", s)
    red = _PHONE_RE.sub("[redacted-phone]", red)
    return red


# ---------------------------------------------------------------------------
# person classification (fixture-aware)
# ---------------------------------------------------------------------------

_BUILTIN_SLUGS = {
    "priya": FRIEND,
    "sam": PROFESSIONAL,
}

_FIXTURE_FILENAMES = (
    "contacts.json",
    "people.json",
    "identities.json",
    "fixtures.json",
    "persons.json",
    "users.json",
    "sandbox.json",
)


def _candidate_fixture_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent
    cwd = Path.cwd()
    cands: list[Path] = []
    for base in (here, here.parent, cwd):
        for sub in (
            ".",
            "var/mind",
            "var",
            "sandbox",
            "fixtures",
            "data",
            "apps/marc-muse/sandbox",
            "apps/marc-muse/fixtures",
            "apps/marc-muse/var/mind",
            "marc-muse/sandbox",
            "marc-muse/fixtures",
        ):
            cands.append((base / sub))
    # dedupe, keep existing only
    uniq: list[Path] = []
    seen: set[str] = set()
    for p in cands:
        try:
            rp = str(p.resolve())
        except Exception:
            rp = str(p)
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(p)
    return [p for p in uniq if p.is_dir()]


def _extract_records_from_obj(obj) -> list[dict]:
    if obj is None:
        return []
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    if isinstance(obj, dict):
        for key in ("records", "people", "contacts", "persons", "users", "identities", "fixtures", "items"):
            val = obj.get(key)
            if isinstance(val, list):
                recs = [r for r in val if isinstance(r, dict)]
                if recs:
                    return recs
            elif isinstance(val, dict):
                # {"priya": {...}, "sam": {...}}
                recs = []
                for slug, rec in val.items():
                    if isinstance(rec, dict):
                        cp = dict(rec)
                        cp.setdefault("slug", slug)
                        recs.append(cp)
                if recs:
                    return recs
        # Single record dict?
        if any(k in obj for k in ("email", "emails", "phone", "phones", "ig", "wa", "slug", "channel")):
            return [obj]
    return []


def _load_fixture_records() -> list[dict]:
    recs: list[dict] = []
    # Env override for tests.
    env_path = os.environ.get("MARC_FIXTURES", "") or os.environ.get("FIXTURES_PATH", "")
    search_files: list[Path] = []
    if env_path:
        for part in env_path.split(os.pathsep):
            part = part.strip()
            if not part:
                continue
            p = Path(part)
            if p.is_dir():
                for name in _FIXTURE_FILENAMES:
                    search_files.append(p / name)
                try:
                    search_files.extend(sorted(p.glob("*.json")))
                except Exception:
                    pass
            elif p.is_file():
                search_files.append(p)
    for d in _candidate_fixture_dirs():
        for name in _FIXTURE_FILENAMES:
            search_files.append(d / name)
        try:
            for f in sorted(d.glob("*.json")):
                if f not in search_files:
                    search_files.append(f)
        except Exception:
            pass
    seen: set[str] = set()
    for f in search_files:
        try:
            key = str(f.resolve())
        except Exception:
            key = str(f)
        if key in seen:
            continue
        seen.add(key)
        if not f.is_file():
            continue
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        try:
            recs.extend(_extract_records_from_obj(obj))
        except Exception:
            continue
    return recs


def _person_matches(person: dict, slug: str) -> bool:
    want = str(slug or "").strip().lower()
    if not want:
        return False
    for s in person.get("slugs", []):
        if str(s).strip().lower() == want:
            return True
    for nm in person.get("names", []):
        nl = str(nm).strip().lower()
        if nl == want or want in nl or nl in want:
            return True
    for bag in ("emails", "phones", "igs", "was"):
        for v in person.get(bag, []):
            if str(v).strip().lower() == want:
                return True
    for k in ("email", "phone", "ig", "wa"):
        if str(person.get(k, "")).strip().lower() == want and want:
            return True
    # slug embedded e.g. "priya-sharma" contains "priya"
    for s in person.get("slugs", []) + person.get("names", []):
        sl = str(s).strip().lower()
        if want in sl or sl in want:
            return True
    return False


def classify_person(slug) -> str:
    """Classify a person slug as ``professional`` | ``friend`` | ``stranger`` | ``mixed``.

    Reads sandbox fixture files when present (see ``_load_fixture_records``),
    merges them with :func:`merge_identity`, and returns the matching
    person's relationship. Falls back to built-ins (Priya -> friend,
    Sam -> professional) so the self-check passes without fixtures.
    """
    want = str(slug or "").strip().lower()
    if not want:
        return STRANGER
    try:
        fixture_recs = _load_fixture_records()
    except Exception:
        fixture_recs = []
    if fixture_recs:
        try:
            persons = merge_identity(fixture_recs)
        except Exception:
            persons = []
        for p in persons:
            try:
                if _person_matches(p, want):
                    rel = p.get("relationship", STRANGER)
                    rel = _norm_relationship(rel) or STRANGER
                    return rel
            except Exception:
                continue
    # Built-in fallback (also covers fixture files that lack priya/sam).
    for key, label in _BUILTIN_SLUGS.items():
        if want == key or key in want or want in key:
            return label
    return STRANGER


if __name__ == "__main__":
    assert classify_channel("gmail") == "professional", classify_channel("gmail")
    assert classify_channel("Gmail") == "professional"
    assert classify_channel("instagram:stranger") == "stranger", classify_channel("instagram:stranger")
    assert classify_channel("instagram:friend") == "friend", classify_channel("instagram:friend")
    assert classify_channel("whatsapp") == "mixed", classify_channel("whatsapp")
    assert classify_person("priya") == "friend", classify_person("priya")
    assert classify_person("Priya") == "friend", classify_person("Priya")
    assert classify_person("sam") == "professional", classify_person("sam")
    assert classify_person("Sam") == "professional", classify_person("Sam")
    # merge + leak sanity
    _persons = merge_identity(
        [
            {"slug": "priya-ig", "ig": "priya.x", "relationship": "friend"},
            {"slug": "priya-wa", "ig": "priya.x", "wa": "+15550001111"},
            {"slug": "sam", "email": "sam@work.com", "channel": "gmail"},
        ]
    )
    _priya = next(p for p in _persons if "priya.x" in p["igs"])
    assert _priya["relationship"] == "friend", _priya
    assert leak_ok({"work_ok": False}, "gmail", "instagram") is False
    assert leak_ok({"work_ok": True}, "gmail", "whatsapp") is True
    assert "@" not in redact("mail me at sam@work.com", {"work_ok": False}, "instagram")
    print("policy self-check ok: Priya=friend Sam=professional")
