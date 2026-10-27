"""Bee control planner + dispatch (stdlib re only).

Mirrors apps/bee-android/bee_ask.py behavior but normalizes tool names to:
whatsapp_send, play_music, mail_compose, dial, open_app, type_into.
"""
import re

SPARK_MODEL = "muse-spark-1.3"
WONDER_MODEL = "muse-wonder-1.0"

__all__ = [
    "skip_muse",
    "split_clauses",
    "clause_to_tool",
    "split_utterance",
    "classify_voice",
    "this_or_that",
    "decide",
    "plan_ask",
    "dispatch",
]


def skip_muse(text):
    if not isinstance(text, str):
        if text is None:
            return False
        try:
            text = str(text)
        except Exception:
            return False
    low = text.lower()
    if re.search(r'\bdemo\b', low):
        return False
    if 'email' in low or 'whatsapp' in low:
        return False
    try:
        clauses = split_clauses(text)
    except Exception:
        clauses = [text]
    if isinstance(clauses, list) and len(clauses) > 1:
        return False
    if ';' in text:
        return False
    if re.search(r'\bafter\s+that\b', low):
        return False
    if re.search(r'\bthen\b', low):
        return False
    if re.search(r'\band\b\s+(?:text|whatsapp|play|email|mail|call|dial|open|type)\b', low):
        return False
    if re.search(r',\s*(?:and\s+)?(?:text|whatsapp|play|email|mail|call|dial|open)\b', low):
        return False
    stripped = low.strip()
    if stripped.startswith('type '):
        return True
    if re.match(r'open\s+spotify\b', stripped):
        return True
    if 'youtube' in low:
        return True
    return False


def split_clauses(text):
    if not isinstance(text, str):
        if text is None:
            return []
        try:
            text = str(text)
        except Exception:
            return []
    if text.strip() == '':
        return []
    pat = (
        r'\s*;\s*'
        r'|\s*,?\s*\bafter\s+that\b\s*,?\s*'
        r'|\s*,?\s*\band\s+then\b\s*,?\s*'
        r'|\s*,?\s*\bthen\b\s*,?\s*'
        r'|\s*(?:,\s*(?:and\s+)?|\band\b\s+)(?=(?:text|whatsapp|play|email|mail|call|dial|open)\b)'
    )
    parts = re.split(pat, text, flags=re.IGNORECASE)
    out = []
    for p in parts:
        if p is None:
            continue
        s = p.strip()
        if s == '':
            continue
        out.append(s)
    return out


class _ToolResult(dict):
    def __init__(self, tool, args, device):
        super(_ToolResult, self).__init__(tool=tool, args=args, device=device)
        self._ordered = (tool, args, device)

    def __iter__(self):
        return iter(self._ordered)

    def __len__(self):
        return 3

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._ordered[key]
        return super(_ToolResult, self).__getitem__(key)

    def __getattr__(self, name):
        if name in ('tool', 'args', 'device'):
            try:
                return self[name]
            except KeyError:
                raise AttributeError(name)
        raise AttributeError(name)

    def __eq__(self, other):
        if isinstance(other, (list, tuple)):
            try:
                if len(other) != 3:
                    return False
                return self._ordered[0] == other[0] and self._ordered[1] == other[1] and self._ordered[2] == other[2]
            except Exception:
                return False
        if isinstance(other, dict):
            try:
                return dict(self) == dict(other)
            except Exception:
                return False
        return False

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq is NotImplemented:
            return eq
        return not eq


def clause_to_tool(clause):
    if not isinstance(clause, str):
        if clause is None:
            clause = ''
        else:
            try:
                clause = str(clause)
            except Exception:
                clause = ''
    low_raw = clause.lower()
    device = 'laptop' if 'on my laptop' in low_raw else 'phone'
    cleaned = re.sub(r'\bon\s+my\s+laptop\b', '', clause, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    m = re.match(r'^\s*(?:text|whatsapp)\s+(\S+)(?:\s+(.*))?$', cleaned, flags=re.IGNORECASE)
    if m:
        to = (m.group(1) or '').strip()
        rest = (m.group(2) or '').strip() if m.group(2) is not None else ''
        args = {'to': to, 'text': rest}
        return _ToolResult('whatsapp_send', args, device)
    m = re.match(r'^\s*play\b\s*(.*)$', cleaned, flags=re.IGNORECASE)
    if m:
        if re.match(r'^\s*play\b', cleaned, flags=re.IGNORECASE):
            query = (m.group(1) or '').strip()
            args = {'query': query}
            return _ToolResult('play_music', args, device)
    m = re.match(r'^\s*(?:email|mail)\s+(\S+)(?:\s+(.*))?$', cleaned, flags=re.IGNORECASE)
    if m:
        to = (m.group(1) or '').strip()
        subj = (m.group(2) or '').strip() if m.group(2) is not None else ''
        args = {'to': to, 'subject': subj}
        return _ToolResult('mail_compose', args, device)
    m = re.match(r'^\s*(?:call|dial)\b\s*(.*)$', cleaned, flags=re.IGNORECASE)
    if m:
        if re.match(r'^\s*(?:call|dial)\b', cleaned, flags=re.IGNORECASE):
            to = (m.group(1) or '').strip()
            args = {'to': to}
            return _ToolResult('dial', args, device)
    m = re.match(r'^\s*open\b\s*(.*)$', cleaned, flags=re.IGNORECASE)
    if m:
        if re.match(r'^\s*open\b', cleaned, flags=re.IGNORECASE):
            app = (m.group(1) or '').strip()
            args = {'app': app}
            return _ToolResult('open_app', args, device)
    m = re.match(r'^\s*type\b\s*(.*)$', cleaned, flags=re.IGNORECASE)
    if m:
        if re.match(r'^\s*type\b', cleaned, flags=re.IGNORECASE):
            txt = (m.group(1) or '').strip()
            args = {'text': txt}
            return _ToolResult('type_into', args, device)
    return _ToolResult(None, {}, device)


def split_utterance(text):
    if not isinstance(text, str):
        if text is None:
            return []
        try:
            text = str(text)
        except Exception:
            return []
    if text.strip() == '':
        return []
    clauses = split_clauses(text)
    if not clauses:
        return []
    low_text = text.lower()
    positions = []
    pos = 0
    for cl in clauses:
        low_cl = cl.lower()
        try:
            idx = low_text.find(low_cl, pos)
        except Exception:
            idx = -1
        if idx == -1:
            idx = pos
            end = pos + len(low_cl)
        else:
            end = idx + len(low_cl)
        positions.append((idx, end))
        pos = end
    steps = []
    for i, cl in enumerate(clauses):
        try:
            res = clause_to_tool(cl)
        except Exception:
            continue
        try:
            if isinstance(res, dict):
                tool = res.get('tool')
                args = res.get('args')
                device = res.get('device')
            else:
                tool = res[0]
                args = res[1]
                device = res[2]
        except Exception:
            continue
        if tool is None:
            continue
        if args is None:
            args = {}
        if device is None:
            device = 'phone'
        sid = 's%d' % (len(steps) + 1)
        if len(steps) == 0:
            after = []
        else:
            try:
                gap = low_text[positions[i - 1][1]:positions[i][0]]
            except Exception:
                gap = ''
            if re.search(r'\bthen\b', gap) or re.search(r'\bafter\s+that\b', gap):
                try:
                    prev_id = steps[-1].get('id') if isinstance(steps[-1], dict) else ('s%d' % len(steps))
                except Exception:
                    prev_id = 's%d' % len(steps)
                after = [prev_id]
            else:
                after = []
        step = {'id': sid, 'tool': tool, 'args': args, 'device': device, 'after': after}
        steps.append(step)
    return steps


def classify_voice(text):
    if not isinstance(text, str):
        if text is None:
            text = ''
        else:
            try:
                text = str(text)
            except Exception:
                text = ''
    low = text.lower()
    if 'reboot' in low or 'shutdown' in low or 'sudo' in low or 'poweroff' in low or 'rm -rf' in low:
        return {'kind': 'refuse'}
    if re.search(r'\bsend\s+it\b', low):
        return {'kind': 'confirm'}
    if re.search(r'\b(yes|yeah|yep|okay)\b', low):
        return {'kind': 'confirm'}
    if re.search(r'\bok\b', low):
        return {'kind': 'confirm'}
    if re.search(r'\bdo\s+it\b', low):
        return {'kind': 'confirm'}
    if re.search(r'\bgo\s+ahead\b', low):
        return {'kind': 'confirm'}
    try:
        _stripped = low.strip().strip('?.!. ').strip()
    except Exception:
        _stripped = low.strip()
    if _stripped == 'that':
        return {'kind': 'confirm'}
    if re.search(r'\b(nope|cancel|stop)\b', low):
        return {'kind': 'cancel'}
    if re.search(r'\bno\b', low):
        return {'kind': 'cancel'}
    return {'kind': 'ask'}


def this_or_that(steps):
    try:
        if not steps:
            return ''
    except Exception:
        return ''
    try:
        seq = list(steps)
    except Exception:
        return ''
    if len(seq) == 0:
        return ''
    if len(seq) > 1:
        return 'Do this: %d tools?' % len(seq)
    try:
        first = seq[0]
    except Exception:
        return ''
    tool = None
    args = {}
    try:
        if isinstance(first, dict):
            tool = first.get('tool')
            _a = first.get('args')
            if isinstance(_a, dict):
                args = _a
            elif _a is None:
                args = {}
            else:
                args = {}
        elif isinstance(first, (list, tuple)) and len(first) >= 1:
            tool = first[0]
            try:
                _a2 = first[1] if len(first) > 1 else {}
                args = _a2 if isinstance(_a2, dict) else {}
            except Exception:
                args = {}
        else:
            return 'Do this: 1 tool?'
    except Exception:
        return 'Do this: 1 tool?'
    if not tool:
        return 'Do this: 1 tool?'
    try:
        t = str(tool)
    except Exception:
        return 'Do this: 1 tool?'
    label = ''
    try:
        if t == 'play_music':
            q = ''
            try:
                q = str(args.get('query', '') or '').strip()
            except Exception:
                q = ''
            q = re.sub(r'\s+', ' ', q).strip()
            label = ('play %s' % q).strip() if q else 'play music'
        elif t == 'whatsapp_send':
            to = ''
            try:
                to = str(args.get('to', '') or '').strip()
            except Exception:
                to = ''
            to = re.sub(r'\s+', ' ', to).strip()
            label = ('text %s' % to).strip() if to else 'send text'
        elif t == 'mail_compose':
            to = ''
            try:
                to = str(args.get('to', '') or '').strip()
            except Exception:
                to = ''
            to = re.sub(r'\s+', ' ', to).strip()
            label = ('email %s' % to).strip() if to else 'send email'
        elif t == 'dial':
            to = ''
            try:
                to = str(args.get('to', '') or '').strip()
            except Exception:
                to = ''
            to = re.sub(r'\s+', ' ', to).strip()
            label = ('call %s' % to).strip() if to else 'call'
        elif t == 'open_app':
            app = ''
            try:
                app = str(args.get('app', '') or '').strip()
            except Exception:
                app = ''
            app = re.sub(r'\s+', ' ', app).strip()
            label = ('open %s' % app).strip() if app else 'open app'
        elif t == 'type_into':
            txt = ''
            try:
                txt = str(args.get('text', '') or '').strip()
            except Exception:
                txt = ''
            txt = re.sub(r'\s+', ' ', txt).strip()
            label = ('type %s' % txt).strip() if txt else 'type'
        else:
            label = t.replace('_', ' ').strip() or '1 tool'
    except Exception:
        label = t.replace('_', ' ').strip() or '1 tool'
    label = re.sub(r'\s+', ' ', label).strip()
    if not label:
        return 'Do this: 1 tool?'
    s = 'Do this: %s?' % label
    if len(s) <= 40:
        return s
    max_label = 40 - len('Do this: ') - len('?')
    if max_label < 1:
        max_label = 1
    label = label[:max_label].rstrip()
    s = 'Do this: %s?' % label
    if len(s) > 40:
        s = s[:40]
    return s


def decide(kind, pending_steps=None):
    try:
        if isinstance(kind, dict):
            k = kind.get('kind')
        else:
            k = kind
    except Exception:
        k = None
    try:
        if k is not None:
            k = str(k).strip().lower()
        else:
            k = None
    except Exception:
        k = None
    has_pending = False
    try:
        if pending_steps is None:
            has_pending = False
        else:
            try:
                has_pending = len(pending_steps) > 0
            except Exception:
                has_pending = bool(pending_steps)
    except Exception:
        has_pending = False
    if k == 'confirm':
        return {'action': 'run' if has_pending else 'ack'}
    if k == 'cancel':
        return {'action': 'drop'}
    if k == 'refuse':
        return {'action': 'refuse'}
    if k == 'ask':
        if not has_pending:
            return {'action': 'ack'}
        return {'action': 'ask'}
    if not has_pending:
        return {'action': 'ack'}
    return {'action': 'ask'}


def plan_ask(text, spark_tools=None, long=False):
    if not isinstance(text, str):
        if text is None:
            text = ''
        else:
            try:
                text = str(text)
            except Exception:
                text = ''
    try:
        cv = classify_voice(text)
        kind = cv.get('kind') if isinstance(cv, dict) else None
    except Exception:
        kind = None
    if kind == 'refuse':
        return {'steps': [], 'model': SPARK_MODEL, 'mode': 'refuse', 'kind': 'refuse'}
    try:
        sk = skip_muse(text)
    except Exception:
        sk = False
    if sk:
        try:
            steps = split_utterance(text)
        except Exception:
            steps = []
        if not steps:
            low = text.lower()
            dev = 'laptop' if 'on my laptop' in low else 'phone'
            m = re.match(r'^\s*type\b\s*(.*)$', text, flags=re.IGNORECASE)
            if m:
                q = (m.group(1) or '').strip()
                steps = [{'id': 's1', 'tool': 'type_into', 'args': {'text': q}, 'device': dev, 'after': []}]
            else:
                try:
                    r = clause_to_tool(text)
                    if isinstance(r, dict) and r.get('tool'):
                        steps = [{'id': 's1', 'tool': r.get('tool'), 'args': r.get('args'), 'device': r.get('device'), 'after': []}]
                    else:
                        steps = [{'id': 's1', 'tool': 'local_fast', 'args': {'text': text.strip()}, 'device': dev, 'after': []}]
                except Exception:
                    steps = [{'id': 's1', 'tool': 'local_fast', 'args': {'text': text.strip()}, 'device': dev, 'after': []}]
        return {'steps': steps, 'model': 'local_fast', 'mode': 'local_fast', 'kind': 'local_fast'}
    try:
        steps2 = split_utterance(text)
    except Exception:
        steps2 = []
    if isinstance(steps2, list) and len(steps2) >= 2:
        return {'steps': steps2, 'model': SPARK_MODEL, 'mode': 'dag', 'kind': 'dag'}
    if isinstance(spark_tools, list) and len(spark_tools) > 0:
        return {'steps': list(spark_tools), 'model': SPARK_MODEL, 'mode': 'spark', 'kind': 'spark'}
    try:
        is_long = bool(long) or len(text) > 80
    except Exception:
        is_long = bool(long)
    if is_long:
        return {'steps': [], 'model': WONDER_MODEL, 'mode': 'wonder', 'kind': 'wonder'}
    return {'steps': [], 'model': SPARK_MODEL, 'mode': 'spark', 'kind': 'spark'}


def dispatch(steps, run_phone, run_laptop, laptop_ok=True):
    results = []
    if steps is None:
        return results
    try:
        seq = list(steps)
    except Exception:
        return results
    for step in seq:
        if not isinstance(step, dict):
            continue
        try:
            tool = step.get('tool')
        except Exception:
            continue
        if tool is None:
            continue
        try:
            device = step.get('device')
        except Exception:
            device = 'phone'
        try:
            dlow = str(device).lower() if device is not None else 'phone'
        except Exception:
            dlow = 'phone'
        is_laptop = dlow in ('laptop', 'server')
        if is_laptop:
            if laptop_ok:
                results.append(run_laptop(step))
            else:
                try:
                    sid = step.get('id')
                except Exception:
                    sid = None
                results.append({'id': sid, 'ok': False, 'error': 'laptop offline'})
        else:
            results.append(run_phone(step))
    return results
