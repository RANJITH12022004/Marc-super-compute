"""SQLite FTS5 index over markdown mind dir (stdlib only).

Layout:
    <mind_dir>/index/mind.sqlite

Tables:
    chunks(id INTEGER PRIMARY KEY, path TEXT, heading TEXT, text TEXT, tokens TEXT)
    chunks_fts  -- FTS5 virtual table over (path, heading, text, tokens)

No third-party deps (no sqlite-vec). The ``tokens`` column holds
space-joined lowercase word tokens and :func:`search` computes a simple
token-overlap score used as the vector-ish rank.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

__all__ = ["rebuild", "search", "get_db_path"]

DB_REL = Path("index") / "mind.sqlite"
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_SCHEMA_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    tokens TEXT NOT NULL DEFAULT ''
);
"""

_SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
USING fts5(path, heading, text, tokens, tokenize='porter');
"""


def _default_mind_dir() -> Path:
    for name in ("MARC_MIND_DIR", "MIND_DIR"):
        raw = os.environ.get(name)
        if raw:
            return Path(raw)
    # Fall back to sibling config default (./var/mind) without importing it
    # (package dir contains a hyphen so normal imports are fragile).
    try:
        cfg_path = Path(__file__).resolve().parents[1] / "config.py"
        if cfg_path.exists():
            pass
    except Exception:
        pass
    return Path("./var/mind")


def _resolve_mind_dir(mind_dir: str | Path | None) -> Path:
    if mind_dir is None:
        return _default_mind_dir()
    return Path(mind_dir)


def get_db_path(mind_dir: str | Path | None = None) -> Path:
    """Return the sqlite file path for *mind_dir*."""
    return _resolve_mind_dir(mind_dir) / DB_REL


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _init_db(con: sqlite3.Connection) -> None:
    con.execute(_SCHEMA_CHUNKS)
    # FTS table may fail on builds without FTS5; fall back gracefully.
    try:
        con.execute(_SCHEMA_FTS)
    except sqlite3.OperationalError:
        pass
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)"
    )
    con.commit()


def _has_fts(con: sqlite3.Connection) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
    ).fetchone()
    return row is not None


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens used for the ``tokens`` column."""
    return _TOKEN_RE.findall((text or "").lower())


def _chunk_markdown(path_rel: str, content: str) -> list[tuple[str, str]]:
    """Split markdown *content* into (heading, text) chunks.

    A new chunk starts at each ATX heading line (``#`` .. ``######``).
    Files without headings yield a single chunk with an empty heading.
    Empty chunks are dropped.
    """
    chunks: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, heading
        text = "\n".join(buf).strip()
        # Drop pure-empty chunks but keep chunks that only have a heading.
        if text or heading:
            body = (heading + "\n" + text).strip() if heading else text
            if body:
                chunks.append((heading, body))
        buf = []

    for line in content.splitlines():
        stripped = line.lstrip()
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", stripped)
        if m:
            flush()
            heading = m.group(2).strip()
        else:
            buf.append(line)
    flush()
    return chunks


def _iter_markdown_files(mind_dir: Path):
    for path in sorted(mind_dir.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(mind_dir)
        except ValueError:
            continue
        # Exclude anything under a raw/ directory.
        if "raw" in rel.parts:
            continue
        yield path, rel.as_posix()


def rebuild(mind_dir: str | Path | None = None) -> int:
    """Rebuild the index from scratch. Idempotent; returns chunk count."""
    base = _resolve_mind_dir(mind_dir)
    db_path = base / DB_REL
    con = _connect(db_path)
    try:
        _init_db(con)
        # Clear existing rows (idempotent rebuild).
        con.execute("DELETE FROM chunks")
        if _has_fts(con):
            try:
                con.execute("DELETE FROM chunks_fts")
            except sqlite3.OperationalError:
                pass
        count = 0
        if base.is_dir():
            for path, rel in _iter_markdown_files(base):
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for heading, text in _chunk_markdown(rel, content):
                    toks = tokenize(heading + " " + text)
                    tokens_col = " ".join(toks)
                    cur = con.execute(
                        "INSERT INTO chunks (path, heading, text, tokens)"
                        " VALUES (?, ?, ?, ?)",
                        (rel, heading, text, tokens_col),
                    )
                    rowid = cur.lastrowid
                    if _has_fts(con):
                        try:
                            con.execute(
                                "INSERT INTO chunks_fts"
                                " (rowid, path, heading, text, tokens)"
                                " VALUES (?, ?, ?, ?, ?)",
                                (rowid, rel, heading, text, tokens_col),
                            )
                        except sqlite3.OperationalError:
                            pass
                    count += 1
        con.commit()
        return count
    finally:
        con.close()


def _fts_match_expr(qtokens: list[str]) -> str | None:
    parts = []
    for tok in qtokens:
        clean = tok.replace('"', "").strip()
        if not clean:
            continue
        parts.append('"%s"' % clean)
    if not parts:
        return None
    return " OR ".join(parts)


def search(
    query: str,
    limit: int = 8,
    mind_dir: str | Path | None = None,
) -> list[dict]:
    """Full-text search. Returns [{path, heading, snippet, score}].

    ``score`` is the simple token-overlap count (vector-ish rank);
    FTS5 ``bm25`` is used only as a tiebreaker. Falls back to a
    LIKE/overlap scan when FTS5 is unavailable or matches nothing.
    """
    base = _resolve_mind_dir(mind_dir)
    db_path = base / DB_REL
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 8
    n = max(1, min(n, 100))
    qtokens = tokenize(query or "")
    if not qtokens:
        return []
    qset = set(qtokens)

    if not db_path.exists():
        return []

    con = _connect(db_path)
    try:
        try:
            _init_db(con)
        except sqlite3.OperationalError:
            pass
        rows: list[dict] = []
        use_fts = _has_fts(con)
        match = _fts_match_expr(qtokens) if use_fts else None
        if match is not None:
            try:
                cur = con.execute(
                    "SELECT c.path AS path, c.heading AS heading,"
                    " c.text AS text, c.tokens AS tokens,"
                    " snippet(chunks_fts, 2, '<b>', '</b>', '...', 32) AS snippet,"
                    " bm25(chunks_fts) AS rank"
                    " FROM chunks AS c"
                    " JOIN chunks_fts ON c.id = chunks_fts.rowid"
                    " WHERE chunks_fts MATCH ?"
                    " ORDER BY rank LIMIT ?",
                    (match, n * 5),
                )
                for r in cur.fetchall():
                    toks = set((r["tokens"] or "").split())
                    overlap = len(qset & toks)
                    snippet = r["snippet"] or (r["text"] or "")[:240]
                    try:
                        rank = float(r["rank"])
                    except (TypeError, ValueError):
                        rank = 0.0
                    rows.append(
                        {
                            "path": r["path"],
                            "heading": r["heading"] or "",
                            "snippet": snippet,
                            "score": float(overlap),
                            "_rank": rank,
                            "_overlap": overlap,
                        }
                    )
            except sqlite3.OperationalError:
                rows = []
        if not rows:
            # Fallback: overlap scan over all chunks.
            try:
                cur = con.execute(
                    "SELECT path, heading, text, tokens FROM chunks LIMIT 5000"
                )
            except sqlite3.OperationalError:
                return []
            for r in cur.fetchall():
                toks = set((r["tokens"] or "").split())
                overlap = len(qset & toks)
                if overlap <= 0:
                    continue
                text = r["text"] or ""
                rows.append(
                    {
                        "path": r["path"],
                        "heading": r["heading"] or "",
                        "snippet": text[:240],
                        "score": float(overlap),
                        "_rank": 0.0,
                        "_overlap": overlap,
                    }
                )
        # Vector-ish ranking: overlap desc, bm25 asc.
        rows.sort(key=lambda d: (-d["_overlap"], d["_rank"]))
        out = []
        for d in rows[:n]:
            out.append(
                {
                    "path": d["path"],
                    "heading": d["heading"],
                    "snippet": d["snippet"],
                    "score": d["score"],
                }
            )
        return out
    finally:
        con.close()
