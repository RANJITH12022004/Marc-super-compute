"""Form playground + filler — sandbox-safe (stdlib only).

Local fake form lives at ``sandbox/forms/demo.html`` (FAKE sandbox banner,
``name`` / ``email`` / ``message`` fields, no network on submit).

Helpers here never touch the network:

- :func:`parse_fields` uses stdlib :mod:`html.parser` and returns
  ``[{name, type, label}]`` for an HTML file.
- :func:`fill` writes a filled copy of the HTML under
  ``<mind>/drafts/forms/`` (atomic write, values HTML-escaped).
- :func:`optional_playwright` only drives a real page when ``playwright``
  is importable; otherwise it returns
  ``{ok: False, reason: 'playwright not installed — used html filler'}``.

The GET path that serves the filled copy is wired later (server side);
:func:`fill` just returns the file path to serve.
"""

from __future__ import annotations

import html
import os
import re
import uuid
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

__all__ = [
    "mind_dir",
    "forms_dir",
    "demo_html_path",
    "parse_fields",
    "fill",
    "optional_playwright",
    "write_file",
]

_SAFE_STEM = re.compile(r"[^A-Za-z0-9_-]+")


def mind_dir() -> Path:
    raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
    return Path((raw or "").strip() or "./var/mind")


def forms_dir() -> Path:
    """Output dir for filled copies: ``<mind>/drafts/forms``."""
    return mind_dir() / "drafts" / "forms"


def demo_html_path() -> Path:
    """Absolute path of the bundled FAKE sandbox demo form."""
    return Path(os.path.dirname(os.path.abspath(__file__))) / "sandbox" / "forms" / "demo.html"


def write_file(path, text: str) -> Path:
    """Atomic UTF-8 write (tmp + os.replace). Creates parents."""
    target = Path(path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    base = "%s.%d.tmp" % (target.name, os.getpid())
    tmp = parent / base
    counter = 0
    while tmp.exists():
        counter += 1
        tmp = parent / ("%s.%d.%d.tmp" % (target.name, os.getpid(), counter))
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass
    os.replace(tmp, target)
    return target


# ---------------------------------------------------------- parse_fields ---

class _FieldParser(HTMLParser):
    """Collect named form fields plus their <label> text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields: list[dict] = []
        # Completed <label for=...> texts (may appear before or after field).
        self.labels_by_for: dict[str, str] = {}
        # Stack of open <label> elements: {for, chunks, field_idxs}.
        self._label_stack: list[dict] = []

    # -- helpers ------------------------------------------------------
    def _current_label(self):
        return self._label_stack[-1] if self._label_stack else None

    def _add_field(self, name: str, ftype: str, attrs: dict):
        field = {
            "name": name,
            "type": ftype or "text",
            "label": "",
            "id": str(attrs.get("id") or ""),
            "placeholder": str(attrs.get("placeholder") or ""),
            "aria": str(attrs.get("aria-label") or ""),
        }
        idx = len(self.fields)
        self.fields.append(field)
        lab = self._current_label()
        if lab is not None:
            lab.setdefault("field_idxs", []).append(idx)
        return field

    # -- HTMLParser hooks ---------------------------------------------
    def handle_starttag(self, tag, attrs):
        t = str(tag or "").lower()
        attrs_d = {str(k or "").lower(): (v if v is not None else "") for k, v in (attrs or [])}
        if t == "label":
            self._label_stack.append({
                "for": str(attrs_d.get("for") or "").strip(),
                "chunks": [],
                "field_idxs": [],
            })
            return
        if t == "input":
            name = str(attrs_d.get("name") or "").strip()
            if not name:
                return
            ftype = str(attrs_d.get("type") or "text").strip().lower() or "text"
            self._add_field(name, ftype, attrs_d)
        elif t == "textarea":
            name = str(attrs_d.get("name") or "").strip()
            if not name:
                return
            self._add_field(name, "textarea", attrs_d)
        elif t == "select":
            name = str(attrs_d.get("name") or "").strip()
            if not name:
                return
            self._add_field(name, "select", attrs_d)
        # <button>/<keygen>/etc without name are ignored on purpose.

    def handle_data(self, data):
        lab = self._current_label()
        if lab is not None and data:
            lab["chunks"].append(str(data))

    def handle_endtag(self, tag):
        if str(tag or "").lower() != "label":
            return
        if not self._label_stack:
            return
        lab = self._label_stack.pop()
        text = re.sub(r"\s+", " ", "".join(lab.get("chunks") or "")).strip()
        for_id = str(lab.get("for") or "").strip()
        if for_id:
            if text and for_id not in self.labels_by_for:
                self.labels_by_for[for_id] = text
            elif text and not self.labels_by_for.get(for_id):
                self.labels_by_for[for_id] = text
        # Fields wrapped by this label inherit its text when unlabeled.
        if text:
            for idx in (lab.get("field_idxs") or []):
                if 0 <= idx < len(self.fields) and not self.fields[idx].get("label"):
                    self.fields[idx]["label"] = text

    def result(self) -> list[dict]:
        out: list[dict] = []
        for f in self.fields:
            label = str(f.get("label") or "").strip()
            if not label:
                fid = str(f.get("id") or "").strip()
                if fid and fid in self.labels_by_for:
                    label = self.labels_by_for[fid]
            if not label:
                label = str(f.get("aria") or "").strip()
            if not label:
                label = str(f.get("placeholder") or "").strip()
            if not label:
                label = str(f.get("name") or "").strip()
            out.append({
                "name": str(f.get("name") or ""),
                "type": str(f.get("type") or "text"),
                "label": label,
            })
        return out


def parse_fields(html_path) -> list[dict]:
    """Parse an HTML file and return ``[{name, type, label}]`` (stdlib only).

    Looks at ``<input name=...>``, ``<textarea name=...>`` and
    ``<select name=...>``; ``type`` defaults to ``"text"`` for inputs and is
    ``"textarea"`` / ``"select"`` for those tags. ``label`` prefers an
    explicit ``<label for=id>``, then a wrapping ``<label>``, then
    ``aria-label`` / ``placeholder`` / ``name`` as fallback.
    """
    path = Path(html_path)
    text = path.read_text(encoding="utf-8")
    parser = _FieldParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        pass
    return parser.result()


# ------------------------------------------------------------------ fill ---

_INPUT_RE = re.compile(r"<input\b[^>]*>", re.I)
_NAME_RE = re.compile(r"""\bname\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'`>=\/]+))""", re.I)
_VALUE_RE = re.compile(r"""\s*\bvalue\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'`>]+))""", re.I)
_TEXTAREA_RE = re.compile(
    r"<textarea\b([^>]*)>(.*?)</textarea>", re.I | re.S
)
_SELECT_RE = re.compile(r"<select\b([^>]*)>(.*?)</select>", re.I | re.S)
_OPTION_RE = re.compile(r"<option\b([^>]*)>(.*?)</option>", re.I | re.S)
_OPT_VALUE_RE = re.compile(r"""\bvalue\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'`>]+))""", re.I)
_OPT_SELECTED_RE = re.compile(r"""\s*\bselected(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'`>]+))?""", re.I)


def _attr_name(tag_text: str) -> str:
    m = _NAME_RE.search(tag_text or "")
    if not m:
        return ""
    for g in (m.group(2), m.group(3), m.group(4)):
        if g is not None:
            return str(g).strip()
    return ""


def _set_input_value(tag_text: str, value: str) -> str:
    escaped = html.escape(str(value), quote=True)
    cleaned = _VALUE_RE.sub("", tag_text or "")
    # Insert value="..." before the closing ">" (handle "/>").
    stripped = cleaned.rstrip()
    if stripped.endswith("/>"):
        inner = stripped[:-2].rstrip()
        return "%s value=\"%s\" />" % (inner, escaped)
    if stripped.endswith(">"):
        inner = stripped[:-1].rstrip()
        return "%s value=\"%s\">" % (inner, escaped)
    return cleaned + (" value=\"%s\"" % escaped)


def _fill_inputs(text: str, values: dict) -> str:
    def _sub(m: re.Match) -> str:
        tag = m.group(0)
        name = _attr_name(tag)
        if not name or name not in values:
            return tag
        # Checkboxes/radios: set checked instead of value when value matches?
        # Keep it simple: set value attribute; checkable inputs also get checked.
        out = _set_input_value(tag, values[name])
        low = tag.lower()
        if ('type="checkbox"' in low or "type='checkbox'" in low
                or 'type="radio"' in low or "type='radio'" in low):
            if re.search(r"""\bchecked\b""", out, re.I) is None:
                out = out.rstrip()
                if out.endswith("/>"):
                    out = out[:-2].rstrip() + " checked />"
                elif out.endswith(">"):
                    out = out[:-1].rstrip() + " checked>"
        return out

    return _INPUT_RE.sub(_sub, text or "")


def _fill_textareas(text: str, values: dict) -> str:
    def _sub(m: re.Match) -> str:
        attrs = m.group(1) or ""
        name = _attr_name("<textarea " + attrs + ">")
        if not name or name not in values:
            return m.group(0)
        escaped = html.escape(str(values[name]), quote=False)
        return "<textarea%s>%s</textarea>" % (attrs, escaped)

    return _TEXTAREA_RE.sub(_sub, text or "")


def _fill_selects(text: str, values: dict) -> str:
    def _select_sub(m: re.Match) -> str:
        attrs = m.group(1) or ""
        inner = m.group(2) or ""
        name = _attr_name("<select " + attrs + ">")
        if not name or name not in values:
            return m.group(0)
        wanted = str(values[name]).strip()

        def _opt_sub(o: re.Match) -> str:
            o_attrs = o.group(1) or ""
            o_text = o.group(2) or ""
            vm = _OPT_VALUE_RE.search(o_attrs)
            if vm:
                for g in (vm.group(2), vm.group(3), vm.group(4)):
                    if g is not None:
                        opt_val = str(g)
                        break
                else:
                    opt_val = ""
            else:
                opt_val = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", o_text)).strip()
            base = _OPT_SELECTED_RE.sub("", o_attrs).rstrip()
            if opt_val.strip() == wanted or re.sub(
                r"\s+", " ", re.sub(r"<[^>]+>", "", o_text)
            ).strip() == wanted:
                return "<option%s selected>%s</option>" % (base, o_text)
            return "<option%s>%s</option>" % (base, o_text)

        return "<select%s>%s</select>" % (attrs, _OPTION_RE.sub(_opt_sub, inner))

    return _SELECT_RE.sub(_select_sub, text or "")


def _safe_stem(name: str) -> str:
    cleaned = _SAFE_STEM.sub("_", str(name or "").strip()).strip("_")
    return (cleaned or "form")[:80]


def fill(html_path, values: dict | None = None) -> dict:
    """Fill a local HTML form copy with *values* — no network.

    Reads *html_path*, sets ``value`` attributes / ``<textarea>`` bodies /
    ``<select>`` selections for keys in *values*, and writes the filled copy
    under ``<mind>/drafts/forms/<stem>.filled-<stamp>.html`` atomically.

    Returns ``{ok, path, src, fields}`` on success.
    """
    values = dict(values or {})
    src = Path(html_path)
    try:
        original = src.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        return {"ok": False, "error": "read failed: %s" % exc, "src": str(src)}
    try:
        fields = parse_fields(src)
    except Exception:
        fields = []
    filled = _fill_textareas(_fill_selects(_fill_inputs(original, values), values), values)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    stem = _safe_stem(src.stem)
    out_name = "%s.filled-%s-%s.html" % (stem, stamp, suffix)
    try:
        out_dir = forms_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = write_file(out_dir / out_name, filled)
    except OSError as exc:
        return {"ok": False, "error": "write failed: %s" % exc, "src": str(src)}
    return {
        "ok": True,
        "path": str(out_path),
        "src": str(src),
        "fields": fields,
        "values": dict(values),
    }


# --------------------------------------------------- optional_playwright ---

def optional_playwright(url, values: dict | None = None) -> dict:
    """Fill a live URL with playwright when installed, else graceful fallback.

    Returns ``{ok: False, reason: 'playwright not installed — used html filler'}``
    when the ``playwright`` package cannot be imported, so callers can fall
    back to :func:`fill` on the local sandbox form.
    """
    values = dict(values or {})
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return {"ok": False, "reason": "playwright not installed — used html filler"}
    target = str(url or "").strip()
    if not target:
        return {"ok": False, "reason": "missing url"}
    try:
        filled: dict = {}
        errors: dict = {}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(target, wait_until="domcontentloaded", timeout=15000)
                for key, val in values.items():
                    text = str(val)
                    done = False
                    for sel in (
                        'textarea[name="%s"]' % key,
                        'input[name="%s"]' % key,
                        'select[name="%s"]' % key,
                        '#%s' % key,
                    ):
                        try:
                            loc = page.locator(sel).first
                            if loc.count() > 0:
                                try:
                                    loc.fill(text, timeout=3000)
                                except Exception:
                                    try:
                                        loc.select_option(text, timeout=3000)
                                    except Exception:
                                        loc.fill(text, timeout=3000)
                                done = True
                                break
                        except Exception:
                            continue
                    if done:
                        filled[key] = text
                    else:
                        errors[key] = "no matching selector"
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
        if errors and not filled:
            return {"ok": False, "reason": "no fields filled: %s" % sorted(errors),
                    "url": target, "filled": filled, "errors": errors}
        return {"ok": True, "url": target, "filled": filled, "errors": errors}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:300] or "playwright error",
                "url": target}
