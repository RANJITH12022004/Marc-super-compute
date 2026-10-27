#!/usr/bin/env python3
"""Bee-island phone installer (leftover walls).

Pushes the bee-island scaffold to the phone over SSH/SFTP.

Safety walls (must not be removed):
  * REMOTE is '/home/rox/bee/android' -- never point at mark-laptop or marc.
  * assert_safe_path(p) raises on 'mark-laptop' or '/home/rox/marc/android'
    in any slash style (backslashes are normalised before checking).
  * LOCAL sources from apps/bee-island.
  * Secret handling: read the SSH secret from the environment and keep it
    out of stdout/logs.

Stdlib + paramiko only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from pathlib import PurePosixPath

try:
    import paramiko
except ImportError:  # pragma: no cover - exercised on device/laptop with paramiko
    paramiko = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]

# LOCAL sources from apps/bee-island
LOCAL = ROOT / "apps/bee-island"

REMOTE = '/home/rox/bee/android'

_SECRET_ENV = "MARC_SSH_PW"


def assert_safe_path(p) -> str:
    """Reject leftover-dangerous destinations.

    Raises ValueError if the path touches 'mark-laptop' or
    '/home/rox/marc/android' (any slash style). Returns the normalised
    (backslash -> slash) string otherwise.
    """
    s = str(p).replace("\\", "/")
    if "mark-laptop" in s:
        raise ValueError(f"refusing unsafe path (mark-laptop): {p!r}")
    if "/home/rox/marc/android" in s:
        raise ValueError(f"refusing unsafe path (marc android): {p!r}")
    return s


def remote_join(*parts: str) -> str:
    """Join REMOTE with relative parts and enforce the safety walls."""
    assert_safe_path(REMOTE)
    for part in parts:
        assert_safe_path(part)
    joined = str(PurePosixPath(REMOTE, *[str(x).replace("\\", "/").lstrip("/") for x in parts]))
    assert_safe_path(joined)
    return joined


def iter_local_files(base: Path = LOCAL):
    """Yield (local_path, rel_posix) for every file under LOCAL."""
    assert_safe_path(str(base))
    for path in sorted(base.rglob("*")):
        if path.is_file():
            rel = path.relative_to(base).as_posix()
            # Guard the relative legs too (walls apply everywhere).
            assert_safe_path(rel)
            assert_safe_path(f"{REMOTE}/{rel}")
            yield path, rel


def ensure_remote_dir(ssh, remote_dir: str) -> None:
    """mkdir -p the remote dir over SSH after wall checks."""
    assert_safe_path(remote_dir)
    cmd = f"mkdir -p '{remote_dir}'"
    _, _, stderr = ssh.exec_command(cmd)
    status = stderr.channel.recv_exit_status()
    if status != 0:
        raise RuntimeError(f"mkdir failed for {remote_dir}: status {status}")


def sftp_upload(sftp, local_path: Path, remote_path: str) -> None:
    """Upload one file after wall checks."""
    assert_safe_path(remote_path)
    parent = str(PurePosixPath(remote_path).parent)
    assert_safe_path(parent)
    try:
        sftp.stat(parent)
    except OSError:
        # Caller ensures parent dirs exist.
        raise RuntimeError(f"remote parent missing: {parent}")
    sftp.put(str(local_path), remote_path)


def build_plan(base: Path = LOCAL):
    """Return [(local_path, remote_path)] without touching the network."""
    assert_safe_path(REMOTE)
    assert_safe_path(str(base))
    plan = []
    for local_path, rel in iter_local_files(base):
        plan.append((local_path, remote_join(rel)))
    return plan


def deploy(host: str, port: int, username: str, secret: str, base: Path = LOCAL) -> int:
    """Connect via paramiko and upload every file under LOCAL to REMOTE."""
    if paramiko is None:
        raise RuntimeError("paramiko is required: pip install paramiko")
    assert_safe_path(REMOTE)
    plan = build_plan(base)
    if not plan:
        print(f"nothing to upload under {base}")
        return 0
    print(f"local : {base}")
    print(f"remote: {REMOTE} ({len(plan)} files)")
    print(f"ssh   : {username}@{host}:{port}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=username, password=secret)
    try:
        # Ensure top-level remote dir exists.
        _, _, stderr = client.exec_command(f"mkdir -p '{REMOTE}'")
        stderr.channel.recv_exit_status()
        sftp = client.open_sftp()
        try:
            created: set[str] = set()
            for local_path, remote_path in plan:
                assert_safe_path(remote_path)
                parent = str(PurePosixPath(remote_path).parent)
                if parent not in created:
                    _, _, err = client.exec_command(f"mkdir -p '{parent}'")
                    err.channel.recv_exit_status()
                    created.add(parent)
                sftp.put(str(local_path), remote_path)
                print(f"put {local_path.relative_to(base).as_posix()} -> {remote_path}")
        finally:
            sftp.close()
    finally:
        client.close()
    print("done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host = os.environ.get("MARC_SSH_HOST", "127.0.0.1")
    port = int(os.environ.get("MARC_SSH_PORT", "22"))
    username = os.environ.get("MARC_SSH_USER", "rox")
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        print("SSH secret is not set in the environment; refusing to proceed", file=sys.stderr)
        return 2
    base = LOCAL if not argv else (ROOT / argv[0] if not Path(argv[0]).is_absolute() else Path(argv[0]))
    assert_safe_path(str(base))
    assert_safe_path(REMOTE)
    return deploy(host, port, username, secret, base)


if __name__ == "__main__":
    raise SystemExit(main())
