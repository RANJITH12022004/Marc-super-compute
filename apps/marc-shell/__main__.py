"""marc_shell entry point: replay fake mic lines against the server.

Run as ``python -m marc_shell`` from ``apps/`` (or with ``PYTHONPATH=apps``)::

    cd apps && python -m marc_shell --fake-mic
    PYTHONPATH=apps python -m marc_shell --fake-mic --context driving
"""

import argparse
import os
import sys

try:
    from .fake_mic import replay
    from . import client
except ImportError:  # allow `python apps/marc-shell/__main__.py` fallback
    from fake_mic import replay  # type: ignore
    import client  # type: ignore


def _is_wake_or_sleep(line):
    """Return True for wake-word / sleep lines that should not be POSTed."""
    low = line.strip().lower()
    if low in ("hey marc", "sleep", "stop marc"):
        return True
    if "stop marc" in low:
        return True
    if "sleep" in low.split():
        return True
    return False


def build_parser():
    p = argparse.ArgumentParser(prog="marc_shell", description="marc-shell fake-mic runner")
    p.add_argument("--url", default="http://127.0.0.1:8096")
    p.add_argument("--token", default=os.environ.get("MARC_TOKEN"))
    p.add_argument("--context", default="desk", choices=["desk", "driving"])
    p.add_argument("--fake-mic", dest="fake_mic", action="store_true")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.fake_mic:
        for line in replay():
            print(line)
            sys.stdout.flush()
            if _is_wake_or_sleep(line):
                continue
            try:
                resp = client.post_utterance(args.url, args.token, line, context=args.context)
                print(resp)
            except Exception as e:
                print("error: %s" % e)
        return 0

    parser.print_usage(sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
