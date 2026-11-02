"""Laptop home ingest walker (stdlib only).

:func:`walk_home` walks a laptop home directory (default ``USERPROFILE``
or ``HOME``), skips denied/secret paths, ingests only small text-like
files, writes truncated digests to ``notes/laptop/<safe>.md`` under the
mind vault, and rebuilds the SQLite index.

Deny (any match skips the file; denied dirs are pruned):
    - ``.env`` files / path components
    - ``credentials`` in the filename (e.g. credentials.json)
    - ``.pem`` files
    - ``.ssh`` directories
    - ``Temp`` directories (case-insensitive ``temp``)
    - ``node_modules`` directories
    - ``.git/objects`` paths
    - ``.apk`` files
    - ``browser`` in any path component
    - ``Login Data`` files (Chrome)
    - ``local.properties`` files (Android)

Allow (plus size cap):
    - extensions ``.md`` ``.txt`` ``.py`` ``.java``
    - files named ``README`` (``README``, ``README.md``, ``README_*`` ...)
    - size ``<= MAX_FILE_BYTES`` (files larger than the cap are skipped)

Notes:
    ``<mind>/notes/laptop/<safe>.md`` where ``<safe>`` is the relative
    path sanitized to a flat filename ending in ``.md``. The digest is
    the first ``DIGEST_LIMIT`` characters plus a ``[truncated]`` marker.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = [
    "walk_home",
    "default_home_root",
    "is_denied",
    "is_allowed",
    "safe_note_name",
    "MAX_FILE_BYTES",
    "SIZE_CAP",
    "MAX_BYTES",
    "MAX_SIZE",
    "DIGEST_LIMIT",
    "TRUNCATE_LIMIT",
    "DIGEST_MAX",
    "ALLOWED_EXTS",
]

MAX_FILE_BYTES = 200_000
SIZE_CAP = MAX_FILE_BYTES
MAX_BYTES = MAX_FILE_BYTES
MAX_SIZE = MAX_FILE_BYTES

DIGEST_LIMIT = 8000
TRUNCATE_LIMIT = DIGEST_LIMIT
DIGEST_MAX = DIGEST_LIMIT

ALLOWED_EXTS = frozenset({".md", ".txt", ".py", ".java"})


def _resolve_mind_dir(mind_dir: str | Path | None = None) -> Path:
    if mind_dir is not None and str(mind_dir).strip():
        return Path(str(mind_dir).strip())
    for key in ("MARC_MIND_DIR", "MIND_DIR"):
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            return Path(str(raw).strip())
    return Path("./var/mind")


def default_home_root() -> Path:
    """Return USERPROFILE or HOME, else Path.home()."""
    for key in ("USERPROFILE", "HOME"):
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            return Path(str(raw).strip())
    try:
        return Path.home()
    except Exception:
        return Path(".")


def _rel_posix(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(os.path.relpath(str(path), str(root)))
    return rel.as_posix()


def is_denied(rel_posix: str) -> str | None:
    """Return deny reason for a home-relative posix path, else None."""
    rel = (rel_posix or "").replace("\\", "/").strip()
    if not rel:
        return None
    low_rel = rel.lower()
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    low_parts = [p.lower() for p in parts]
    name = parts[-1] if parts else rel
    low_name = name.lower()

    # .env files / components
    if ".env" in low_parts:
        return ".env"
    if low_name == ".env" or low_name.startswith(".env."):
        return ".env"
    # credentials in filename
    if "credentials" in low_name:
        return "credentials"
    # .pem files
    if low_name.endswith(".pem"):
        return ".pem"
    # .ssh dirs
    if ".ssh" in low_parts:
        return ".ssh"
    # Temp dirs (case-insensitive)
    if "temp" in low_parts:
        return "Temp"
    # node_modules dirs
    if "node_modules" in low_parts:
        return "node_modules"
    # .git/objects paths
    if ".git/objects" in low_rel:
        return ".git/objects"
    if ".git" in low_parts and "objects" in low_parts:
        try:
            gi = low_parts.index(".git")
            # objects must appear at or after .git
            if "objects" in low_parts[gi:]:
                return ".git/objects"
        except ValueError:
            pass
    # apk files
    if low_name.endswith(".apk"):
        return "apk"
    # browser in any component
    for p in low_parts:
        if "browser" in p:
            return "browser"
    # Login Data (Chrome)
    if low_name == "login data":
        return "Login Data"
    # local.properties (Android)
    if low_name == "local.properties":
        return "local.properties"
    return None


def is_allowed(filename: str) -> bool:
    """Return True for allowed ingest filenames (md/txt/py/java/README)."""
    base = os.path.basename(str(filename or ""))
    if not base:
        return False
    low = base.lower()
    if low == "readme" or low.startswith("readme.") or low.startswith("readme_") or low.startswith("readme-"):
        return True
    try:
        suffix = Path(base).suffix.lower()
    except Exception:
        suffix = ""
    return suffix in ALLOWED_EXTS


def safe_note_name(rel_posix: str) -> str:
    """Map a home-relative posix path to a flat ``*.md`` filename."""
    base = (rel_posix or "").replace("\\", "/").strip().strip("/")
    if not base:
        base = "file"
    flat = base.replace("/", "__")
    flat = re.sub(r"[^A-Za-z0-9_.\-]+", "_", flat).strip("._")
    if not flat:
        flat = "file"
    # Keep total reasonable; preserve trailing .md handling.
    if len(flat) > 120:
        flat = flat[:120].rstrip("._") or "file"
    if flat.lower().endswith(".md"):
        return flat
    return flat + ".md"


def _atomic_write(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / ("%s.%d.tmp" % (path.name, os.getpid()))
    counter = 0
    cand = tmp
    while cand.exists():
        counter += 1
        cand = path.parent / ("%s.%d.%d.tmp" % (path.name, os.getpid(), counter))
    tmp = cand
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass
    os.replace(tmp, path)
    return path


def _rebuild_index(mind: Path) -> int:
    try:
        from .index import rebuild as _rebuild  # type: ignore
        return int(_rebuild(mind))
    except Exception:
        pass
    try:
        import importlib.util as _ilu

        cand = Path(__file__).resolve().parent / "index.py"
        if cand.is_file():
            spec = _ilu.spec_from_file_location("_laptop_ingest_index", str(cand))
            if spec is not None and spec.loader is not None:
                mod = _ilu.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                fn = getattr(mod, "rebuild", None)
                if callable(fn):
                    return int(fn(mind))
    except Exception:
        pass
    return 0


def walk_home(root=None, mind_dir=None, **kwargs) -> dict:
    """Walk laptop home, write truncated digests, rebuild index.

    Args:
        root: home directory to walk. Defaults to ``USERPROFILE`` or
            ``HOME`` when None/empty. Also accepts ``home``/``homedir``
            kwargs for compatibility.
        mind_dir: mind vault directory. Defaults to ``MARC_MIND_DIR`` /
            ``MIND_DIR`` / ``./var/mind``. Also accepts ``mind`` kwarg.

    Returns:
        ``{ok, root, mind_dir, count, ingested, files, notes, ...}``.
        ``count``/``ingested`` is the number of notes written.
    """
    # Compatibility kwargs.
    if root is None or (isinstance(root, str) and not root.strip()):
        for key in ("home", "homedir", "home_dir", "directory", "dir"):
            try:
                cand = kwargs.get(key)
            except Exception:
                cand = None
            if cand is not None and str(cand).strip():
                root = cand
                break
    if mind_dir is None:
        for key in ("mind", "mindDir", "minddir"):
            try:
                cand = kwargs.get(key)
            except Exception:
                cand = None
            if cand is not None and str(cand).strip():
                mind_dir = cand
                break

    if root is None or (isinstance(root, str) and not str(root).strip()):
        root_path = default_home_root()
    else:
        try:
            root_path = Path(str(root).strip())
        except Exception:
            return {"ok": False, "error": "bad root", "root": str(root), "count": 0, "ingested": 0, "files": [], "notes": []}

    mind = _resolve_mind_dir(mind_dir)

    try:
        if not root_path.is_dir():
            return {
                "ok": False,
                "error": "missing root: %s" % str(root_path),
                "root": str(root_path),
                "mind_dir": str(mind),
                "count": 0,
                "ingested": 0,
                "files": [],
                "notes": [],
            }
    except Exception as exc:
        return {"ok": False, "error": "bad root: %s" % exc, "root": str(root_path), "mind_dir": str(mind), "count": 0, "ingested": 0, "files": [], "notes": []}

    try:
        mind.mkdir(parents=True, exist_ok=True)
        (mind / "notes" / "laptop").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    files: list[str] = []
    notes: list[str] = []
    skipped = 0
    denied = 0
    oversized = 0
    disallowed = 0

    for cur_dir, dirnames, filenames in os.walk(str(root_path), topdown=True, followlinks=False):
        try:
            cur_p = Path(cur_dir)
        except Exception:
            continue
        # Prune denied dirs in-place.
        kept: list[str] = []
        for d in list(dirnames):
            try:
                full = cur_p / d
                rel = _rel_posix(full, root_path)
            except Exception:
                continue
            # Check the dir path itself plus a synthetic child to catch
            # prefix denies (e.g. Temp, node_modules, .ssh, browser).
            reason = is_denied(rel) or is_denied(rel + "/_probe.txt")
            if reason is not None:
                denied += 0  # dirs counted via files skipped; keep count stable
                continue
            kept.append(d)
        dirnames[:] = sorted(kept)
        for fn in sorted(filenames):
            try:
                full = cur_p / fn
                rel = _rel_posix(full, root_path)
            except Exception:
                skipped += 1
                continue
            reason = is_denied(rel)
            if reason is not None:
                denied += 1
                skipped += 1
                continue
            if not is_allowed(fn):
                disallowed += 1
                skipped += 1
                continue
            try:
                st = full.stat()
                size = int(st.st_size)
            except OSError:
                skipped += 1
                continue
            except Exception:
                skipped += 1
                continue
            if size > MAX_FILE_BYTES:
                oversized += 1
                skipped += 1
                continue
            try:
                if not full.is_file():
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                skipped += 1
                continue
            except Exception:
                skipped += 1
                continue
            digest = text[:DIGEST_LIMIT]
            was_truncated = len(text) > DIGEST_LIMIT
            if was_truncated:
                digest = digest.rstrip() + "\n\n[truncated %d/%d chars]\n" % (len(digest), len(text))
            header = "# Laptop: %s\n\n- Source: %s\n- Size: %d bytes\n\n" % (rel, rel, size)
            body = header + digest
            if not body.endswith("\n"):
                body += "\n"
            dest = mind / "notes" / "laptop" / safe_note_name(rel)
            try:
                _atomic_write(dest, body)
            except OSError:
                skipped += 1
                continue
            except Exception:
                skipped += 1
                continue
            files.append(rel)
            try:
                notes.append(str(dest))
            except Exception:
                notes.append(rel)

    chunks = 0
    rebuild_error = ""
    try:
        chunks = _rebuild_index(mind)
    except Exception as exc:
        rebuild_error = str(exc)[:200]

    out: dict = {
        "ok": True,
        "root": str(root_path),
        "mind_dir": str(mind),
        "count": len(files),
        "ingested": len(files),
        "files": files,
        "notes": notes,
        "written": list(notes),
        "skipped": skipped,
        "denied": denied,
        "oversized": oversized,
        "disallowed": disallowed,
        "chunks": chunks,
    }
    if rebuild_error:
        out["rebuild_error"] = rebuild_error
    return out
