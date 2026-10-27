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
    skip_parts = {"__pycache__", ".gradle", "build"}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        if path.suffix == ".pyc":
            continue
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


def _exec(ssh, cmd: str, timeout: int = 120) -> tuple[int, str, str]:
    """Run a remote command. Never logs the SSH secret."""
    assert_safe_path(REMOTE)
    if "mark-laptop" in cmd.replace("\\", "/") or cmd.strip().startswith("rm -rf"):
        raise ValueError("refusing unsafe remote command")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def assemble_remote(ssh) -> str:
    """Copy wrapper from the old tree (read-only) into REMOTE, then assembleDebug.

    Never writes /home/rox/marc/android or any mark-laptop path.
    Returns the remote APK path.
    """
    assert_safe_path(REMOTE)
    gradle_home = "/home/rox/bee/gradle-8.9"
    assert_safe_path(gradle_home)
    script = (
        "set -e; "
        "mkdir -p '%s' '%s'; "
        "printf 'sdk.dir=/home/rox/android-sdk\\n' > '%s/local.properties'; "
        "if [ ! -x '%s/bin/gradle' ]; then "
        "  cd /home/rox/bee; "
        "  curl -fsSL -o gradle-8.9-bin.zip "
        "    https://services.gradle.org/distributions/gradle-8.9-bin.zip; "
        "  unzip -qo gradle-8.9-bin.zip; "
        "fi; "
        "cd '%s'; "
        "'%s/bin/gradle' --no-daemon :app:assembleDebug"
    ) % (
        REMOTE, gradle_home,
        REMOTE,
        gradle_home,
        REMOTE,
        gradle_home,
    )
    print("assemble: :app:assembleDebug at /home/rox/bee/android")
    code, out, err = _exec(ssh, script, timeout=600)
    sys.stdout.write(out)
    sys.stderr.write(err)
    if code != 0:
        raise RuntimeError("assembleDebug failed")
    apk = remote_join("app/build/outputs/apk/debug/app-debug.apk")
    assert_safe_path(apk)
    return apk


def pull_apk(sftp, remote_apk: str, local_apk: Path) -> Path:
    assert_safe_path(remote_apk)
    local_apk.parent.mkdir(parents=True, exist_ok=True)
    sftp.get(remote_apk, str(local_apk))
    print("apk -> %s" % local_apk.name)
    return local_apk


def adb_install(local_apk: Path) -> int:
    """Install com.bee.island. Never targets com.marc.island."""
    adb = os.environ.get(
        "MARC_ADB",
        r"C:\Users\ranjith\Downloads\platform-tools\adb.exe",
    )
    import subprocess
    cmd = [adb, "install", str(local_apk)]
    print("adb install (com.bee.island)")
    p = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(p.stdout or "")
    sys.stderr.write(p.stderr or "")
    if p.returncode != 0:
        # Reinstall of the NEW package only.
        cmd = [adb, "install", "-r", str(local_apk)]
        print("adb install -r (com.bee.island only)")
        p = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(p.stdout or "")
        sys.stderr.write(p.stderr or "")
    return p.returncode


def deploy_assemble_install(host: str, port: int, username: str, secret: str) -> int:
    n = deploy(host, port, username, secret, LOCAL)
    if n != 0:
        return n
    if paramiko is None:
        raise RuntimeError("paramiko is required: pip install paramiko")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=username, password=secret)
    try:
        apk_remote = assemble_remote(client)
        sftp = client.open_sftp()
        try:
            local_apk = ROOT / "var" / "bee-island-debug.apk"
            pull_apk(sftp, apk_remote, local_apk)
        finally:
            sftp.close()
    finally:
        client.close()
    return adb_install(ROOT / "var" / "bee-island-debug.apk")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host = os.environ.get("MARC_SSH_HOST", "127.0.0.1")
    port = int(os.environ.get("MARC_SSH_PORT", "22"))
    username = os.environ.get("MARC_SSH_USER", "rox")
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        print("SSH secret is not set in the environment; refusing to proceed", file=sys.stderr)
        return 2
    base = LOCAL
    assemble = False
    for arg in argv:
        if arg in ("--assemble", "--install"):
            assemble = True
        else:
            base = ROOT / arg if not Path(arg).is_absolute() else Path(arg)
    assert_safe_path(str(base))
    assert_safe_path(REMOTE)
    if assemble:
        return deploy_assemble_install(host, port, username, secret)
    return deploy(host, port, username, secret, base)


if __name__ == "__main__":
    raise SystemExit(main())
