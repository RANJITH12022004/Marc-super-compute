"""Runtime configuration loaded from environment variables (stdlib only).

Environment variables (``MARC_``-prefixed names take precedence, unprefixed
aliases are accepted for convenience):

- ``MARC_PLANNER`` / ``PLANNER``: planner identifier (default "").
- ``MARC_MODE`` / ``MODE``: ``sandbox`` (default) or ``live`` / others.
- ``MARC_CONTEXT`` / ``CONTEXT``: ``desk`` (default) or ``driving``.
- ``MARC_BIND`` / ``BIND`` / ``HOST``: bind address (default ``127.0.0.1``).
- ``MARC_PORT`` / ``PORT``: port (default ``8096``).
- ``MARC_TOKEN`` / ``TOKEN`` / ``MARC_AUTH_TOKEN``: auth token (default "").
- ``MARC_MIND_DIR`` / ``MIND_DIR``: mind directory (default ``./var/mind``).
- ``MARC_CREDIT_DAILY_CAP`` / ``CREDIT_DAILY_CAP``: daily USD cap (default ``8.0``).
- ``MARC_SPARK_MODEL`` / ``SPARK_MODEL``: spark model name (default "").
- ``MARC_WONDER_MODEL`` / ``WONDER_MODEL``: wonder model name (default "").
- ``MARC_MAX_HOPS`` / ``MAX_HOPS``: max hops (default ``8``).
- ``MARC_HARD_HOPS`` / ``HARD_HOPS``: hard hops (default ``14``).
- ``MARC_CONFIRM_TOOLS`` / ``CONFIRM_TOOLS``: comma-separated tool names.
- ``MARC_MUSE_URL`` / ``MUSE_URL``: muse URL (default "").
- ``MARC_LAPTOP_URL`` / ``LAPTOP_URL``: laptop URL (default "").
- ``MODEL_API_KEY`` / ``META_API_KEY``: model API key (default "").
- ``META_WA_TOKEN`` / ``WHATSAPP_TOKEN``: Meta WhatsApp placeholder.
- ``META_IG_TOKEN`` / ``INSTAGRAM_TOKEN``: Meta Instagram placeholder.
- ``META_PHONE_NUMBER_ID`` / ``META_VERIFY_TOKEN``: extra Meta placeholders.
- ``MARC_GOOGLE_TOKEN_PATH`` / ``GOOGLE_TOKEN_PATH``: google token path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _get(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value != "":
            return value
    return default


def _get_int(*names: str, default: int) -> int:
    raw = _get(*names, default="")
    if raw == "":
        return default
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default


def _get_float(*names: str, default: float) -> float:
    raw = _get(*names, default="")
    if raw == "":
        return default
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return default


def _parse_confirm_tools(raw: str) -> frozenset[str]:
    if not raw:
        return frozenset()
    parts = (p.strip() for p in raw.split(","))
    return frozenset(p for p in parts if p)


def _normalize_context(raw: str | None) -> str:
    """Normalize a raw context value to ``desk`` or ``driving``."""
    value = str(raw or "").strip().lower()
    if value in ("desk", "driving"):
        return value
    return "desk"


@dataclass(frozen=True)
class Settings:
    planner: str = ""
    mode: str = "sandbox"
    bind: str = "127.0.0.1"
    port: int = 8096
    token: str = ""
    mind_dir: Path = field(default_factory=lambda: Path("./var/mind"))
    credit_daily_cap: float = 8.0
    spark_model: str = ""
    wonder_model: str = ""
    max_hops: int = 8
    hard_hops: int = 14
    confirm_tools: frozenset[str] = field(default_factory=frozenset)
    muse_url: str = ""
    laptop_url: str = ""
    model_api_key: str = ""
    meta_wa_token: str = ""
    meta_ig_token: str = ""
    meta_phone_number_id: str = ""
    meta_verify_token: str = ""
    google_token_path: Path = field(default_factory=lambda: Path("./var/mind/google_token.json"))
    context: str = "desk"


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build a :class:`Settings` from the environment (or a supplied mapping)."""
    if env is not None:
        def pick(*names: str, default: str = "") -> str:
            for name in names:
                if name in env and env[name] not in (None, ""):
                    return str(env[name])
            return default
    else:
        pick = _get  # type: ignore[assignment]

    def pick_int(*names: str, default: int) -> int:
        raw = pick(*names, default="")
        if raw == "":
            return default
        try:
            return int(str(raw).strip())
        except ValueError:
            return default

    def pick_float(*names: str, default: float) -> float:
        raw = pick(*names, default="")
        if raw == "":
            return default
        try:
            return float(str(raw).strip())
        except ValueError:
            return default

    mind_dir_raw = pick("MARC_MIND_DIR", "MIND_DIR", default="./var/mind")
    mind_dir = Path(mind_dir_raw)

    google_raw = pick("MARC_GOOGLE_TOKEN_PATH", "GOOGLE_TOKEN_PATH", default="")
    if google_raw:
        google_token_path = Path(google_raw)
    else:
        google_token_path = mind_dir / "google_token.json"

    context_raw = pick("MARC_CONTEXT", "CONTEXT", default="desk")
    context = _normalize_context(context_raw)

    return Settings(
        planner=pick("MARC_PLANNER", "PLANNER", default=""),
        mode=pick("MARC_MODE", "MODE", default="sandbox"),
        bind=pick("MARC_BIND", "BIND", "HOST", default="127.0.0.1"),
        port=pick_int("MARC_PORT", "PORT", default=8096),
        token=pick("MARC_TOKEN", "MARC_AUTH_TOKEN", "TOKEN", default=""),
        mind_dir=mind_dir,
        credit_daily_cap=pick_float(
            "MARC_CREDIT_DAILY_CAP", "CREDIT_DAILY_CAP", default=8.0
        ),
        spark_model=pick("MARC_SPARK_MODEL", "SPARK_MODEL", default=""),
        wonder_model=pick("MARC_WONDER_MODEL", "WONDER_MODEL", default=""),
        max_hops=pick_int("MARC_MAX_HOPS", "MAX_HOPS", default=8),
        hard_hops=pick_int("MARC_HARD_HOPS", "HARD_HOPS", default=14),
        confirm_tools=_parse_confirm_tools(
            pick("MARC_CONFIRM_TOOLS", "CONFIRM_TOOLS", default="")
        ),
        muse_url=pick("MARC_MUSE_URL", "MUSE_URL", default=""),
        laptop_url=pick("MARC_LAPTOP_URL", "LAPTOP_URL", default=""),
        model_api_key=pick("MODEL_API_KEY", "META_API_KEY", default=""),
        meta_wa_token=pick(
            "META_WA_TOKEN", "WHATSAPP_TOKEN", "MARC_WA_TOKEN", default=""
        ),
        meta_ig_token=pick(
            "META_IG_TOKEN", "INSTAGRAM_TOKEN", "MARC_IG_TOKEN", default=""
        ),
        meta_phone_number_id=pick(
            "META_PHONE_NUMBER_ID", "MARC_PHONE_NUMBER_ID", default=""
        ),
        meta_verify_token=pick(
            "META_VERIFY_TOKEN", "MARC_VERIFY_TOKEN", default=""
        ),
        google_token_path=google_token_path,
        context=context,
    )


SETTINGS: Settings = load_settings()


def get_settings() -> Settings:
    """Return the module-level settings snapshot."""
    return SETTINGS


def is_sandbox(mode: str | None = None) -> bool:
    """Return True when the runtime mode is sandbox (default mode)."""
    current = mode if mode is not None else SETTINGS.mode
    return str(current or "").strip().lower() == "sandbox"


def is_driving(context: str | Settings | None = None) -> bool:
    """Return True only when the context is ``driving``."""
    if context is None:
        current = SETTINGS.context
    elif isinstance(context, Settings):
        current = context.context
    else:
        current = str(context or "")
    return current.strip().lower() == "driving"


def hop_cap(context: str | Settings | None = None) -> int:
    """Return the hop cap: 6 when driving, else ``max_hops`` (default 8)."""
    if isinstance(context, Settings):
        if context.context.strip().lower() == "driving":
            return 6
        return context.max_hops
    if is_driving(context):
        return 6
    return SETTINGS.max_hops


def require_confirm(tool: str, confirm: frozenset[str] | None = None) -> bool:
    """Return True when *tool* requires explicit confirmation."""
    tools = confirm if confirm is not None else SETTINGS.confirm_tools
    return str(tool or "").strip() in tools


__all__ = [
    "Settings",
    "SETTINGS",
    "get_settings",
    "load_settings",
    "is_sandbox",
    "is_driving",
    "hop_cap",
    "require_confirm",
]
