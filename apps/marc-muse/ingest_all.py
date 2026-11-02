"""One-shot personal brain ingest: exports + Gmail + GitHub + reindex.

Usage::

    python -m ingest_all
    python ingest_all.py --export path/to/wa.txt

Sandbox by default (FAKE Gmail/GitHub). Live needs MARC_MODE=live + tokens.
Stdlib only.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _ensure_path() -> None:
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))


def run(
    export: str | None = None,
    mind_dir: str | None = None,
    skip_mail: bool = False,
    skip_github: bool = False,
    skip_laptop: bool = True,
) -> dict:
    _ensure_path()
    if mind_dir:
        os.environ["MARC_MIND_DIR"] = str(mind_dir)

    out: dict = {"ok": True, "steps": {}}

    try:
        from brain import vault as _vault

        _vault.seed()
    except Exception as exc:
        out["steps"]["seed"] = {"ok": False, "error": str(exc)[:200]}

    if export:
        try:
            import ingest as _ingest

            res = _ingest.ingest_path(export)
            out["steps"]["export"] = res if isinstance(res, dict) else {"ok": True, "result": str(res)}
        except Exception as exc:
            out["steps"]["export"] = {"ok": False, "error": str(exc)[:200]}
            out["ok"] = False

    if not skip_mail:
        try:
            from connectors import google as _google

            out["steps"]["mail"] = _google.fetch_mail_digest()
        except Exception as exc:
            out["steps"]["mail"] = {"ok": False, "error": str(exc)[:200]}
            out["ok"] = False

    if not skip_github:
        try:
            from connectors import github as _gh

            out["steps"]["github"] = _gh.ingest_repos()
        except Exception as exc:
            out["steps"]["github"] = {"ok": False, "error": str(exc)[:200]}
            out["ok"] = False

    if not skip_laptop:
        try:
            from brain import laptop_ingest as _li

            out["steps"]["laptop"] = _li.walk_home()
        except Exception as exc:
            out["steps"]["laptop"] = {"ok": False, "error": str(exc)[:200]}
            out["ok"] = False

    try:
        from brain import index as _idx

        mind = mind_dir or os.environ.get("MARC_MIND_DIR") or "./var/mind"
        n = _idx.rebuild(mind)
        out["steps"]["reindex"] = {"ok": True, "chunks": n}
    except Exception as exc:
        out["steps"]["reindex"] = {"ok": False, "error": str(exc)[:200]}
        out["ok"] = False

    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ingest personal sources into mind vault")
    p.add_argument("--export", default="", help="WhatsApp/IG/mail export path")
    p.add_argument("--mind-dir", default="", help="Override MARC_MIND_DIR")
    p.add_argument("--skip-mail", action="store_true")
    p.add_argument("--skip-github", action="store_true")
    p.add_argument("--laptop", action="store_true", help="Also walk USERPROFILE/HOME")
    args = p.parse_args(argv)
    res = run(
        export=args.export or None,
        mind_dir=args.mind_dir or None,
        skip_mail=bool(args.skip_mail),
        skip_github=bool(args.skip_github),
        skip_laptop=not bool(args.laptop),
    )
    print(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
