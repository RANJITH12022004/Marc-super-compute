# Only live edit: set MARC_PLANNER=muse and call plan_with_muse() instead of plan_with_needle().
import json
import os
import urllib.request


def plan_with_muse(text, note='', context='', session=''):
    url = os.environ.get('MARC_MUSE_URL', 'http://127.0.0.1:8096/plan')
    headers = {'Content-Type': 'application/json'}
    token = os.environ.get('MARC_TOKEN', '')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = json.dumps({'text': text, 'note': note, 'context': context, 'session_id': session, 'session': session}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {'reply': "Muse isn't running.", 'steps': [], 'plan': [], 'session_id': session}
    plan = data.get('plan', []) or []
    steps = [{'device': p.get('device', ''), 'tool': p.get('tool', ''), 'args': p.get('args', {})} for p in plan]
    return {'reply': data.get('reply', ''), 'steps': steps, 'plan': plan, 'session_id': data.get('session_id', session)}
