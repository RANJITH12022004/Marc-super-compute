"""Meta Responses API client (stdlib only, Python 3.11+).

Port of ``src/meta.js``. Streams Server-Sent Events from
``POST https://api.meta.ai/v1/responses``.

- Bearer auth, never printed/logged.
- Captures ``response.id`` ONLY from ``json["response"]["id"]``.
- Retries without ``previous_response_id`` on
  ``referenced response not found or expired`` errors.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

BASE = "https://api.meta.ai/v1"
RESPONSES_URL = f"{BASE}/responses"

_EXPIRED_RE = re.compile(r"referenced response not found|expired", re.IGNORECASE)


def user_message(text: str) -> dict[str, Any]:
    """Wrap user text as a Responses API message item."""
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }


def _text_from_delta(delta: Any) -> str:
    if isinstance(delta, str):
        return delta
    if isinstance(delta, dict) and isinstance(delta.get("text"), str):
        return str(delta["text"])
    return ""


def _error_message(payload: Any, fallback: str) -> str:
    if not payload:
        return fallback
    if not isinstance(payload, str):
        payload = str(payload)
    try:
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError):
        return payload or fallback
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err:
            return err
        if isinstance(data.get("message"), str) and data["message"]:
            return str(data["message"])
    return payload or fallback


def _is_expired_ref(err: BaseException | str) -> bool:
    msg = str(err.args[0]) if isinstance(err, BaseException) and err.args else str(err)
    if isinstance(err, BaseException) and not err.args:
        msg = str(err)
    return bool(_EXPIRED_RE.search(msg))


def _parse_sse(buffer: str, on_event: Callable[[dict[str, Any]], None]) -> str:
    parts = re.split(r"\r?\n\r?\n", buffer)
    rest = parts.pop() if parts else ""
    for part in parts:
        data = "".join(
            line[5:].strip()
            for line in re.split(r"\r?\n", part)
            if line.startswith("data:")
        )
        if not data or data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            on_event(parsed)
    return rest


def _complete_once(
    key: str,
    model: str,
    instructions: str | None,
    input: Any,  # noqa: A002 - matches Responses API field name
    tools: list[dict[str, Any]] | None = None,
    previous_response_id: str | None = None,
    effort: str = "high",
    timeout: float = 300.0,
    on_text: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": input,
        "reasoning": {"effort": effort},
        "store": True,
        "stream": True,
    }
    if tools:
        body["tools"] = tools
    if previous_response_id:
        body["previous_response_id"] = previous_response_id

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        RESPONSES_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        raise RuntimeError(_error_message(raw, f"Meta API {exc.code}")) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Meta API connection failed: {exc.reason}") from None

    acc: dict[str, dict[str, str]] = {}
    text = ""
    response_id: str | None = None

    def handle(evt: dict[str, Any]) -> None:
        nonlocal text, response_id
        evt_type = str(evt.get("type") or "")
        # ONLY source of truth for the response id.
        response_obj = evt.get("response")
        if isinstance(response_obj, dict) and isinstance(response_obj.get("id"), str):
            response_id = response_obj["id"]

        err_obj = evt.get("error")
        if isinstance(err_obj, dict) and err_obj.get("message"):
            raise RuntimeError(str(err_obj["message"]))
        if evt_type == "response.failed":
            msg = "Meta response failed"
            if isinstance(response_obj, dict):
                nested = response_obj.get("error")
                if isinstance(nested, dict) and nested.get("message"):
                    msg = str(nested["message"])
                elif isinstance(nested, str) and nested:
                    msg = nested
            raise RuntimeError(msg)

        if evt_type == "response.output_text.delta" or evt_type.endswith(
            ".output_text.delta"
        ):
            chunk = _text_from_delta(evt.get("delta"))
            if not chunk and isinstance(evt.get("text"), str):
                chunk = str(evt["text"])
            if chunk:
                text += chunk
                if on_text is not None:
                    on_text(chunk)
            return

        if evt_type in ("response.output_item.added", "response.output_item.done"):
            item = evt.get("item") or {}
            if not isinstance(item, dict):
                return
            if item.get("type") in ("function_call", "tool_call"):
                call_id = item.get("call_id") or item.get("id")
                if not call_id:
                    return
                prev = acc.get(str(call_id)) or {"name": "", "arguments": ""}
                if item.get("name"):
                    prev["name"] = str(item["name"])
                if item.get("arguments"):
                    prev["arguments"] = str(item["arguments"])
                acc[str(call_id)] = prev
            return

        if "function_call_arguments.delta" in evt_type:
            call_id = str(evt.get("item_id") or evt.get("call_id") or "")
            if not call_id:
                return
            prev = acc.get(call_id) or {"name": str(evt.get("name") or ""), "arguments": ""}
            delta = evt.get("delta")
            addition = _text_from_delta(delta)
            if not addition and isinstance(delta, dict):
                raw_args = delta.get("arguments")
                if isinstance(raw_args, str):
                    addition = raw_args
            prev["arguments"] = (prev.get("arguments") or "") + (addition or "")
            if evt.get("name"):
                prev["name"] = str(evt["name"])
            acc[call_id] = prev
            return

        if evt_type == "response.completed":
            output = response_obj.get("output") if isinstance(response_obj, dict) else None
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict) and item.get("type") == "function_call":
                        call_id = item.get("call_id") or item.get("id")
                        if not call_id:
                            continue
                        acc[str(call_id)] = {
                            "name": str(item.get("name") or ""),
                            "arguments": str(
                                item.get("arguments")
                                or acc.get(str(call_id), {}).get("arguments")
                                or ""
                            ),
                        }

    with resp:
        buffer = ""
        while True:
            chunk_bytes = resp.read(4096)
            if not chunk_bytes:
                break
            buffer += chunk_bytes.decode("utf-8", errors="replace")
            buffer = _parse_sse(buffer, handle)
        if buffer.strip():
            _parse_sse(buffer + "\n\n", handle)

    tool_calls = [
        {"callId": call_id, "name": v.get("name", ""), "arguments": v.get("arguments") or "{}"}
        for call_id, v in acc.items()
        if v.get("name")
    ]
    return {"text": text, "tool_calls": tool_calls, "response_id": response_id}


def complete(
    key: str,
    model: str,
    instructions: str | None,
    input: Any,  # noqa: A002 - matches Responses API field name
    tools: list[dict[str, Any]] | None = None,
    previous_response_id: str | None = None,
    fallback_input: Any | None = None,
    effort: str = "high",
    timeout: float = 300.0,
    on_text: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Call the Responses API with SSE streaming.

    Returns ``{"text": str, "tool_calls": [...], "response_id": str|None}``.
    ``tool_calls`` items are ``{"callId": str, "name": str, "arguments": str}``.

    On ``referenced response not found / expired`` errors, retries once
    without ``previous_response_id`` using ``fallback_input`` (full
    conversation) when provided.
    """
    try:
        return _complete_once(
            key,
            model,
            instructions,
            input,
            tools=tools,
            previous_response_id=previous_response_id,
            effort=effort,
            timeout=timeout,
            on_text=on_text,
        )
    except Exception as err:
        if previous_response_id and fallback_input is not None and _is_expired_ref(err):
            return _complete_once(
                key,
                model,
                instructions,
                fallback_input,
                tools=tools,
                previous_response_id=None,
                effort=effort,
                timeout=timeout,
                on_text=on_text,
            )
        raise


__all__ = ["BASE", "RESPONSES_URL", "user_message", "complete"]
