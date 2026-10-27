"""marc-shell client: stdlib-only HTTP client for posting utterances."""

import json
import urllib.request


def utterance_payload(text, context="desk", source="laptop"):
    """Build an utterance payload dict.

    Args:
        text: utterance text.
        context: 'desk' or 'driving'; any other value falls back to 'desk'.
        source: source label (default 'laptop').

    Returns:
        dict with keys {text, context, source}.
    """
    if context not in ("desk", "driving"):
        context = "desk"
    return {"text": text, "context": context, "source": source}


def post_utterance(base_url, token, text, context="desk", source="laptop", opener=None):
    """POST an utterance as JSON and return the parsed JSON response.

    Args:
        base_url: server base URL; POST target is base_url.rstrip('/') + '/utterance'.
        token: bearer token; empty/None raises ValueError('MARC_TOKEN required').
        text: utterance text.
        context: 'desk' or 'driving' (invalid -> 'desk').
        source: source label.
        opener: optional callable used instead of urllib.request.urlopen
            (tests inject a fake). Called as opener(req).

    Returns:
        Parsed JSON dict from the response body.
    """
    if not token:
        raise ValueError("MARC_TOKEN required")
    payload = utterance_payload(text, context=context, source=source)
    data = json.dumps(payload).encode("utf-8")
    url = base_url.rstrip("/") + "/utterance"
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
    )
    open_func = opener if opener is not None else urllib.request.urlopen
    resp = open_func(req)
    # Support both context-manager responses (real urlopen) and
    # plain file-like fakes (tests).
    if hasattr(resp, "__enter__") and hasattr(resp, "__exit__"):
        with resp as r:
            raw = r.read()
    else:
        raw = resp.read()
        try:
            close = getattr(resp, "close", None)
            if callable(close):
                close()
        except Exception:
            pass
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)
