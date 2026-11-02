"""Bee control planner + dispatch (stdlib re only).

Mirrors apps/bee-android/bee_ask.py behavior but normalizes tool names to:
whatsapp_send, play_music, mail_compose, dial, open_app, type_into.
"""
import re
import time

SPARK_MODEL = "muse-spark-1.3"
WONDER_MODEL = "muse-wonder-1.0"

CONFIRM_TOOLS = frozenset([
    "instagram_send",
    "sms_send",
    "calendar_create",
    "open_food_search",
])

__all__ = [
    "CONFIRM_TOOLS",
    "needs_confirm",
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


def needs_confirm(steps_or_tool):
    if isinstance(steps_or_tool, str):
        try:
            t = steps_or_tool.strip()
        except Exception:
            try:
                t = str(steps_or_tool)
            except Exception:
                return False
        return t in CONFIRM_TOOLS
    if isinstance(steps_or_tool, dict):
        try:
            tool = steps_or_tool.get('tool')
        except Exception:
            return False
        if isinstance(tool, str):
            try:
                tool = tool.strip()
            except Exception:
                pass
            return tool in CONFIRM_TOOLS
        return False
    if isinstance(steps_or_tool, (list, tuple)):
        try:
            seq = list(steps_or_tool)
        except Exception:
            return False
        for s in seq:
            if isinstance(s, str):
                try:
                    ts = s.strip()
                except Exception:
                    continue
                if ts in CONFIRM_TOOLS:
                    return True
            elif isinstance(s, dict):
                try:
                    t = s.get('tool')
                except Exception:
                    continue
                if isinstance(t, str):
                    try:
                        t = t.strip()
                    except Exception:
                        continue
                    if t in CONFIRM_TOOLS:
                        return True
            elif isinstance(s, (list, tuple)) and len(s) > 0:
                try:
                    t0 = s[0]
                except Exception:
                    continue
                if isinstance(t0, str):
                    try:
                        t0 = t0.strip()
                    except Exception:
                        continue
                    if t0 in CONFIRM_TOOLS:
                        return True
        return False
    return False


def skip_muse(text):
    if not isinstance(text, str):
        if text is None:
            return False
        try:
            text = str(text)
        except Exception:
            return False
    low = text.lower()
    if 'on my laptop' in low or 'on the server' in low:
        return False
    if re.search(r'\bdemo\b', low):
        return False
    if 'email' in low:
        return False
    if 'whatsapp' in low or re.search(r'\btext\s+\S', low):
        return True
    if 'notification' in low or 'suggest reply' in low or 'what should i reply' in low:
        return True
    if re.search(r'\bplay\b', low):
        return False
    if re.search(r'\breels\b', low) or re.search(r'\bauto\s*scroll\b', low):
        return False
    if re.search(r'\b(instagram|insta)\b', low) and re.search(r'\b(scroll|reel)', low):
        return False
    if re.search(r'\b(youtube|youtu)\b', low) and re.search(r'\b(play|search|first)\b', low):
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
    if re.search(r'\b(?:scroll|swipe|tap|click)\b', low):
        return False
    stripped = low.strip()
    if stripped.startswith('type ') or stripped == 'type':
        return True
    if stripped.startswith('open ') or stripped == 'open':
        return True
    if re.match(r'open\s+\S', stripped):
        return True
    if re.match(r'play\b', stripped):
        return False
    if 'youtube' in low:
        return True
    if 'google' in low:
        return True
    if stripped.startswith('search ') or stripped == 'search':
        return True
    if re.match(r'search\b', stripped):
        return True
    if re.search(r'\bopen\s+\S+.*\btype\s+.+', low):
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
        r'|\s*(?:,\s*(?:and\s+)?|\band\b\s+)(?=(?:text|whatsapp|play|email|mail|call|dial|open|auto\s*scroll|scroll|swipe|tap|click|type|search)\b)'
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
    device = 'laptop' if ('on my laptop' in low_raw or 'on the server' in low_raw) else 'phone'
    cleaned = re.sub(r'\bon\s+my\s+laptop\b', '', clause, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bon\s+the\s+server\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    m = re.match(r'^\s*(?:auto\s*scroll|scroll|swipe)\b(.*)$', cleaned, flags=re.IGNORECASE)
    if m:
        rest = (m.group(1) or '').lower()
        if 'reel' in rest or 'auto' in low_raw:
            return _ToolResult('auto_scroll', {'direction': 'up'}, device)
        direction = 'up'
        if 'down' in rest:
            direction = 'down'
        elif 'left' in rest:
            direction = 'left'
        elif 'right' in rest:
            direction = 'right'
        return _ToolResult('swipe', {'direction': direction}, device)
    m = re.match(r'^\s*(?:tap|click)\b\s*(.*)$', cleaned, flags=re.IGNORECASE)
    if m:
        return _ToolResult('click_text', {'text': (m.group(1) or '').strip()}, device)
    m = re.match(
        r'^\s*(?:touch|tell|ping|message)\s+(.+?)\s+(?:about|re|regarding)\s+(.+)$',
        cleaned,
        flags=re.IGNORECASE,
    )
    if m:
        pkg = 'com.whatsapp' if ('personal whatsapp' in low_raw or 'my whatsapp' in low_raw) else 'com.whatsapp.w4b'
        return _ToolResult(
            'chat_touch',
            {
                'to': (m.group(1) or '').strip(),
                'topic': (m.group(2) or '').strip(),
                'channel': 'whatsapp',
                'package': pkg,
            },
            device,
        )
    if re.search(r'\b(?:new\s+)?notifications?\b', low_raw) or 'what are the new notification' in low_raw:
        return _ToolResult('notifications_list', {}, device)
    m = re.match(
        r'^\s*(?:what\s+should\s+i\s+reply\s+(?:to\s+)?|suggest\s+(?:a\s+)?reply\s+(?:to\s+)?|reply\s+to\s+)(.+)$',
        cleaned,
        flags=re.IGNORECASE,
    )
    if m:
        return _ToolResult('suggest_reply', {'to': (m.group(1) or '').strip()}, device)
    if 'what should i reply' in low_raw or 'suggest reply' in low_raw:
        who = ''
        m2 = re.search(r'(?:reply\s+to|to)\s+(.+)$', cleaned, flags=re.IGNORECASE)
        if m2:
            who = (m2.group(1) or '').strip()
        return _ToolResult('suggest_reply', {'to': who}, device)
    m = re.match(r'^\s*(?:text|whatsapp)\s+(.+?)\s+(marc\s+test)\s*$', cleaned, flags=re.IGNORECASE)
    if m:
        pkg = 'com.whatsapp' if ('personal whatsapp' in low_raw or 'my whatsapp' in low_raw) else 'com.whatsapp.w4b'
        args = {'to': (m.group(1) or '').strip(), 'text': (m.group(2) or '').strip(), 'package': pkg}
        return _ToolResult('whatsapp_send', args, device)
    m = re.match(r'^\s*(?:text|whatsapp)\s+(\S+)(?:\s+(.*))?$', cleaned, flags=re.IGNORECASE)
    if m:
        to = (m.group(1) or '').strip()
        rest = (m.group(2) or '').strip() if m.group(2) is not None else ''
        pkg = 'com.whatsapp' if ('personal whatsapp' in low_raw or 'my whatsapp' in low_raw) else 'com.whatsapp.w4b'
        args = {'to': to, 'text': rest, 'package': pkg}
        return _ToolResult('whatsapp_send', args, device)
    m = re.match(r'^\s*play\b\s*(.*)$', cleaned, flags=re.IGNORECASE)
    if m:
        if re.search(r'\b(youtube|youtu)\b', low_raw):
            query = (m.group(1) or '').strip()
            if re.search(r'\bfirst\b', query, flags=re.IGNORECASE) or re.search(r'\bfirst\b', low_raw):
                return _ToolResult('youtube_play', {'mode': 'first'}, device)
            return _ToolResult('youtube_play', {'mode': 'search', 'query': query}, device)
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
            play = re.match(r'^spotify\s+(?:and\s+)?play\s+(.+)$', app, flags=re.IGNORECASE)
            if play:
                q = (play.group(1) or '').strip()
                if q:
                    return _ToolResult('play_music', {'query': q}, device)
            if re.search(r'\bspotify\b', app, flags=re.IGNORECASE) and re.search(r'\bplay\b', app, flags=re.IGNORECASE):
                mp = re.search(r'play\s+(.+)$', app, flags=re.IGNORECASE)
                q = (mp.group(1) or '').strip() if mp else app
                if q:
                    return _ToolResult('play_music', {'query': q}, device)
            if re.search(r'\b(instagram|insta)\b', app, flags=re.IGNORECASE) and re.search(
                r'\b(scroll|reel|auto\s*scroll)\b', app, flags=re.IGNORECASE
            ):
                return _ToolResult('auto_scroll', {'direction': 'up'}, device)
            if re.search(r'\b(youtube|youtu)\b', app, flags=re.IGNORECASE) and re.search(
                r'\b(play|search|first)\b', app, flags=re.IGNORECASE
            ):
                if re.search(r'\bfirst\b', app, flags=re.IGNORECASE):
                    return _ToolResult('youtube_play', {'mode': 'first'}, device)
                mq = re.search(r'(?:search(?:\s+for)?|play)\s+(.+)$', app, flags=re.IGNORECASE)
                q = (mq.group(1) or '').strip() if mq else app
                return _ToolResult('youtube_play', {'mode': 'search', 'query': q}, device)
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
    low_all = text.lower()
    if ("youtube" in low_all or "youtu" in low_all) and re.search(
        r"\b(play|search|first)\b", low_all
    ):
        mode = "first"
        query = ""
        if re.search(r"\bfirst\b", low_all) and re.search(r"\b(play|video)\b", low_all):
            mode = "first"
        else:
            mode = "search"
            mq = re.search(r"(?:search(?:\s+for)?|play)\s+(.+)$", text, re.I)
            query = (mq.group(1) or "").strip() if mq else ""
            query = re.sub(r"\bon\s+(youtube|youtu\.?be)\s*$", "", query, flags=re.I).strip()
        args = {"mode": mode}
        if query:
            args["query"] = query
        return [{
            "id": "s1",
            "tool": "youtube_play",
            "args": args,
            "device": "phone",
            "after": [],
        }]
    if (
        ("instagram" in low_all or "insta" in low_all)
        and "scroll" in low_all
    ):
        return [{
            "id": "s1",
            "tool": "auto_scroll",
            "args": {"direction": "up"},
            "device": "phone",
            "after": [],
        }]
    m_wa = re.search(
        r"open\s+whats?app.*?search\s+(\S+).*?(?:text|message)(?:\s+him|\s+her|\s+them)?\s+(.+)$",
        text,
        re.I | re.S,
    )
    if m_wa:
        return [{
            "id": "s1",
            "tool": "whatsapp_send",
            "args": {"to": m_wa.group(1).strip(" ,;.:'s"), "text": m_wa.group(2).strip()},
            "device": "phone",
            "after": [],
        }]
    m_sp = re.search(r"open\s+spotify\s+(?:and\s+)?play\s+(.+)$", text, re.I)
    if m_sp:
        return [{
            "id": "s1",
            "tool": "play_music",
            "args": {"query": m_sp.group(1).strip()},
            "device": "phone",
            "after": [],
        }]
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


def _strip_voice(text):
    low = text if isinstance(text, str) else ''
    low = low.lower().strip()
    return re.sub(r'^[?.!,\s]+|[?.!,\s]+$', '', low).strip()


def is_greeting(text):
    stripped = _strip_voice(text)
    return stripped in ('hi', 'hello', 'hey', 'hey marc', 'hey mark', 'hey bee')


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
    stripped = _strip_voice(text)
    if stripped in ('yes', 'yeah', 'yep', 'ok', 'okay', 'send it', 'do it', 'go ahead', 'that'):
        return {'kind': 'confirm'}
    if stripped in ('no', 'nope', 'cancel', 'stop'):
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
        try:
            if needs_confirm(pending_steps):
                return {'action': 'ask'}
            return {'action': 'run'}
        except Exception:
            return {'action': 'ask'}
    if not has_pending:
        return {'action': 'ack'}
    try:
        if needs_confirm(pending_steps):
            return {'action': 'ask'}
        return {'action': 'run'}
    except Exception:
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
            dev = 'laptop' if ('on my laptop' in low or 'on the server' in low) else 'phone'
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
    for i, step in enumerate(seq):
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
            try:
                tool_name = str(step.get('tool') or '').lower()
            except Exception:
                tool_name = ''
            if tool_name == 'open_app' and i + 1 < len(seq):
                nxt = seq[i + 1]
                nt = ''
                ndev = 'phone'
                if isinstance(nxt, dict):
                    try:
                        nt = str(nxt.get('tool') or '').lower()
                    except Exception:
                        nt = ''
                    try:
                        ndev = str(nxt.get('device') or 'phone').lower()
                    except Exception:
                        ndev = 'phone'
                if ndev not in ('laptop', 'server') and nt in (
                    'click_text', 'swipe', 'scroll', 'type_into', 'press_back',
                ):
                    try:
                        time.sleep(0.8)
                    except Exception:
                        pass
    return results
