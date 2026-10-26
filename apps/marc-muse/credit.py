"""File-backed daily credit meter (stdlib only).

State lives at ``<mind_dir>/credit/YYYY-MM-DD.json``::

    {"date": ..., "spark_calls": int, "wonder_calls": int,
     "tokens": int, "usd_estimate": float}

Thread-safe via :class:`threading.Lock`. Never stores any API key.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date as _date
from pathlib import Path
from typing import Any


def _today_str(day: str | None = None) -> str:
    if day:
        return day
    return _date.today().isoformat()


def _coerce_tokens(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_usd(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _empty_state(day: str) -> dict[str, Any]:
    return {
        "date": day,
        "spark_calls": 0,
        "wonder_calls": 0,
        "tokens": 0,
        "usd_estimate": 0.0,
    }


class CreditMeter:
    """Daily usage meter backed by a JSON file per day."""

    def __init__(
        self,
        mind_dir: str | Path | None = None,
        daily_cap: float | None = None,
    ) -> None:
        self._mind_dir = Path(mind_dir) if mind_dir is not None else self._default_mind_dir()
        self._daily_cap = float(daily_cap) if daily_cap is not None else self._default_cap()
        self._lock = threading.Lock()

    # -- resolution helpers (fresh env reads, no API key) -------------------
    @staticmethod
    def _default_mind_dir() -> Path:
        try:
            from apps.marc_muse.config import load_settings as _load  # type: ignore
        except Exception:
            try:
                import config as _cfg  # type: ignore

                _load = _cfg.load_settings  # type: ignore[attr-defined]
            except Exception:
                _load = None  # type: ignore
        if _load is not None:
            try:
                return Path(_load().mind_dir)
            except Exception:
                pass
        raw = os.environ.get("MARC_MIND_DIR") or os.environ.get("MIND_DIR") or "./var/mind"
        return Path(raw)

    @staticmethod
    def _default_cap() -> float:
        raw = os.environ.get("MARC_CREDIT_DAILY_CAP") or os.environ.get("CREDIT_DAILY_CAP")
        if raw not in (None, ""):
            try:
                return float(str(raw).strip())
            except ValueError:
                pass
        try:
            from apps.marc_muse.config import load_settings as _load  # type: ignore
        except Exception:
            try:
                import config as _cfg  # type: ignore

                _load = _cfg.load_settings  # type: ignore[attr-defined]
            except Exception:
                _load = None  # type: ignore
        if _load is not None:
            try:
                return float(_load().credit_daily_cap)
            except Exception:
                pass
        return 8.0

    # -- paths --------------------------------------------------------------
    @property
    def mind_dir(self) -> Path:
        return self._mind_dir

    @property
    def daily_cap(self) -> float:
        return self._daily_cap

    def path_for(self, day: str | None = None) -> Path:
        return self._mind_dir / "credit" / f"{_today_str(day)}.json"

    # -- IO -----------------------------------------------------------------
    def _load_state(self, day: str) -> dict[str, Any]:
        state = _empty_state(day)
        path = self.path_for(day)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return state
        except OSError:
            return state
        try:
            data = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return state
        if not isinstance(data, dict):
            return state
        try:
            state["spark_calls"] = int(data.get("spark_calls", 0) or 0)
        except (TypeError, ValueError):
            state["spark_calls"] = 0
        try:
            state["wonder_calls"] = int(data.get("wonder_calls", 0) or 0)
        except (TypeError, ValueError):
            state["wonder_calls"] = 0
        state["tokens"] = _coerce_tokens(data.get("tokens", 0))
        state["usd_estimate"] = _coerce_usd(data.get("usd_estimate", 0.0))
        state["date"] = day
        return state

    def _save_state(self, state: dict[str, Any], day: str) -> None:
        path = self.path_for(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": day,
            "spark_calls": int(state.get("spark_calls", 0) or 0),
            "wonder_calls": int(state.get("wonder_calls", 0) or 0),
            "tokens": _coerce_tokens(state.get("tokens", 0)),
            "usd_estimate": _coerce_usd(state.get("usd_estimate", 0.0)),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        try:
            tmp.replace(path)
        except OSError:
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # -- public API ---------------------------------------------------------
    def snapshot(self, day: str | None = None) -> dict[str, Any]:
        key = _today_str(day)
        with self._lock:
            return self._load_state(key)

    def usage(self, day: str | None = None) -> dict[str, Any]:
        return self.snapshot(day)

    def add(
        self,
        kind: str,
        tokens: int = 0,
        usd: float = 0.0,
        day: str | None = None,
    ) -> dict[str, Any]:
        key = _today_str(day)
        normalized = str(kind or "").strip().lower()
        with self._lock:
            state = self._load_state(key)
            if normalized in ("spark", "spark_calls", "spark-call", "spark_call"):
                state["spark_calls"] = int(state.get("spark_calls", 0) or 0) + 1
            elif normalized in ("wonder", "wonder_calls", "wonder-call", "wonder_call"):
                state["wonder_calls"] = int(state.get("wonder_calls", 0) or 0) + 1
            state["tokens"] = _coerce_tokens(state.get("tokens", 0)) + _coerce_tokens(tokens)
            state["usd_estimate"] = _coerce_usd(state.get("usd_estimate", 0.0)) + _coerce_usd(usd)
            self._save_state(state, key)
            return dict(state)

    def remaining(self, day: str | None = None) -> float:
        key = _today_str(day)
        with self._lock:
            state = self._load_state(key)
        return float(self._daily_cap) - _coerce_usd(state.get("usd_estimate", 0.0))

    def paused(self, day: str | None = None) -> bool:
        return self.remaining(day) <= 0

    def reset(self, day: str | None = None) -> dict[str, Any]:
        key = _today_str(day)
        with self._lock:
            state = _empty_state(key)
            self._save_state(state, key)
            return dict(state)


_lock = threading.Lock()
_default_meter: CreditMeter | None = None
_default_key: tuple[str, float] | None = None


def _resolve_meter(
    mind_dir: str | Path | None = None,
    daily_cap: float | None = None,
) -> CreditMeter:
    global _default_meter, _default_key
    if mind_dir is not None or daily_cap is not None:
        resolved_dir = Path(mind_dir) if mind_dir is not None else CreditMeter._default_mind_dir()
        resolved_cap = float(daily_cap) if daily_cap is not None else CreditMeter._default_cap()
        return CreditMeter(mind_dir=resolved_dir, daily_cap=resolved_cap)
    resolved_dir = CreditMeter._default_mind_dir()
    resolved_cap = CreditMeter._default_cap()
    key = (str(resolved_dir), float(resolved_cap))
    with _lock:
        if _default_meter is None or _default_key != key:
            _default_meter = CreditMeter(mind_dir=resolved_dir, daily_cap=resolved_cap)
            _default_key = key
        return _default_meter


def snapshot(
    day: str | None = None,
    *,
    mind_dir: str | Path | None = None,
    daily_cap: float | None = None,
) -> dict[str, Any]:
    return _resolve_meter(mind_dir, daily_cap).snapshot(day)


def usage(
    day: str | None = None,
    *,
    mind_dir: str | Path | None = None,
    daily_cap: float | None = None,
) -> dict[str, Any]:
    return _resolve_meter(mind_dir, daily_cap).usage(day)


def add(
    kind: str,
    tokens: int = 0,
    usd: float = 0.0,
    day: str | None = None,
    *,
    mind_dir: str | Path | None = None,
    daily_cap: float | None = None,
) -> dict[str, Any]:
    return _resolve_meter(mind_dir, daily_cap).add(kind, tokens=tokens, usd=usd, day=day)


def remaining(
    day: str | None = None,
    *,
    mind_dir: str | Path | None = None,
    daily_cap: float | None = None,
) -> float:
    return _resolve_meter(mind_dir, daily_cap).remaining(day)


def paused(
    day: str | None = None,
    *,
    mind_dir: str | Path | None = None,
    daily_cap: float | None = None,
) -> bool:
    return _resolve_meter(mind_dir, daily_cap).paused(day)


__all__ = [
    "CreditMeter",
    "add",
    "paused",
    "remaining",
    "snapshot",
    "usage",
]
