#!/usr/bin/env python3
"""Token and $ cost of do-ticket runs, read from Claude Code transcripts after the fact.

  python ticket_cost.py <TICKET_ID>          one ticket: cost per part, main vs sub-agent, by agent type
  python ticket_cost.py --list [--since D]   every ticket found: one line each (D = YYYY-MM-DD)
  options: --projects-dir DIR (default ~/.claude/projects)
           --dispatcher-skill NAME (repeatable): a skill whose invocation also opens a ticket window

Costs nothing to run: no model call, it only reads the .jsonl files on disk.

How a run is found. A main transcript belongs to ticket T from the record that invokes do-ticket for T
(a `Skill` tool call with skill "do-ticket", or a typed `/do-ticket` command) until the next do-ticket
invocation for another ticket, or the end of the file. Time before the first invocation is not counted.
A dispatcher session (one that hands work to other sessions) counts the same way when its skill is
invoked with a ticket id -- name that skill with --dispatcher-skill. A child session (started by another
session) counts from its first record: its brief names the ticket. Without this, a dispatcher run of
PROJ-7028 showed 4 of 8 sessions and $56 of $157.

How a part is found. Inside a window the part starts as `start` and moves on at each marker:
a Read of `do-ticket/phases/<part>.md`, a call to a child skill (SKILL_PART below), or a shell command
that only runs in one part (COMMAND_PART below). The part holds until the next marker.

Sub-agents (`<session>/subagents/agent-*.jsonl`, type from `.meta.json`) are booked to the ticket and
part that were active in the main transcript when the agent started.

Cost. One assistant message is counted once (records that repeat a message id share its usage).
$ = input x in + 5m cache write x 1.25 in + 1h cache write x 2 in + cache read x read + output x out,
with prices per model below; x2 for fast mode on FAST_MODE models. A write with no 5m/1h split is
priced as 1h (what Claude Code wrote when this was measured). A model not in PRICES counts tokens and $0,
and is named in a warning.

Exit codes: 0 report printed · 1 nothing found for that ticket · 2 usage error.
"""
import argparse, bisect, glob, json, os, re, sys
from collections import defaultdict
from datetime import datetime

# USD per million tokens: (input, output, cache read). Source: Anthropic's published model prices, cached
# 2026-09-25. Cache reads are 0.1x input except where the price list says otherwise.
PRICES_AS_OF = '2026-09-25'
PRICES = {
    'claude-fable-5-1': (10.0, 50.0, 0.25),
    'claude-mythos-5-1': (10.0, 50.0, 0.25),
    'claude-fable-5': (10.0, 50.0, 1.00),
    'claude-mythos-5': (10.0, 50.0, 1.00),
    'claude-opus-5-5': (4.0, 20.0, 0.20),
    'claude-opus-5': (5.0, 25.0, 0.50),
    'claude-opus-4-8': (5.0, 25.0, 0.50),
    'claude-opus-4-7': (5.0, 25.0, 0.50),
    'claude-opus-4-6': (5.0, 25.0, 0.50),
    'claude-sonnet-5-5': (2.0, 10.0, 0.20),
    'claude-sonnet-5': (2.0, 10.0, 0.20),
    'claude-sonnet-4-6': (3.0, 15.0, 0.30),
    'claude-haiku-4-5': (1.0, 5.0, 0.10),
}
FAST_MODE = ('claude-opus-5-5', 'claude-opus-5', 'claude-opus-4-8')

PARTS = ('start', 'analyze', 'design', 'build', 'verify', 'ship')
# Child skills that only run inside one part. Add your own child skills here (e.g. a requirements
# writer -> 'analyze', a test-case writer -> 'design', a PR-description writer -> 'ship').
SKILL_PART = {
    'enrich-requirements': 'analyze',
    'push-code': 'verify',
}
TICKET = re.compile(r'\b([A-Z][A-Z0-9]+-\d+[a-z]?)\b')
PHASE_FILE = re.compile(r'do-ticket[\\/]+phases[\\/]+(\w+)\.md', re.I)
# PROJ-11212: the phase files were opened with sed/grep and the verify steps ran as scripts, so no Read/Skill
# marker fired and env-gate..PR was booked under 'build'. Commands that only run in one part move the run into it.
COMMAND_PART = (
    (re.compile(r'sonar-local\.ps1|parse-sonar-issues\.py|check_artifacts\.py\S*\s+\S+\s+pre-(?:commit|push)', re.I), 'verify'),
    (re.compile(r'\bgh\s+pr\s+create\b', re.I), 'ship'),
)
COMMAND = re.compile(r'<command-name>/?([\w:-]+)</command-name>\s*(?:<command-args>([^<]*)</command-args>)?')
RUN_SKILLS = ('do-ticket',)
# The Claude Code app puts this line at the top of a session that another session started.
CHILD_BRIEF = 'Background (from the session that started this one):'
GAP = 600  # seconds; a longer pause is not active time

warnings = defaultdict(set)


def ts(v):
    try:
        return datetime.fromisoformat(v.replace('Z', '+00:00')).timestamp()
    except (AttributeError, ValueError):
        return None


def model_name(m):
    m = re.sub(r'\[[^\]]*\]$', '', m or '')
    return re.sub(r'-\d{8}$', '', m)


def records(path):
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    warnings['torn JSON line skipped'].add(os.path.basename(path))
    except OSError:
        warnings['unreadable file'].add(path)


def cost(usage, model):
    """(tokens dict, $) for one message's usage."""
    cc = usage.get('cache_creation') or {}
    w5, w1 = cc.get('ephemeral_5m_input_tokens'), cc.get('ephemeral_1h_input_tokens')
    write = usage.get('cache_creation_input_tokens') or 0
    if w5 is None and w1 is None:
        w5, w1 = 0, write
    t = {'input': usage.get('input_tokens') or 0, 'write': (w5 or 0) + (w1 or 0),
         'read': usage.get('cache_read_input_tokens') or 0, 'output': usage.get('output_tokens') or 0}
    m = model_name(model)
    if m not in PRICES:
        if m != '<synthetic>':  # Claude Code's own placeholder records, always zero usage
            warnings['model not priced ($0)'].add(m or '?')
        return t, 0.0
    pin, pout, pread = PRICES[m]
    usd = (t['input'] * pin + (w5 or 0) * pin * 1.25 + (w1 or 0) * pin * 2
           + t['read'] * pread + t['output'] * pout) / 1e6
    if usage.get('speed') == 'fast' and m in FAST_MODE:
        usd *= 2
    return t, usd


def user_text(rec):
    content = (rec.get('message') or {}).get('content')
    if isinstance(content, str):
        return content
    return ' '.join(b.get('text', '') for b in content or [] if isinstance(b, dict))


def invocation(rec, run_skills=RUN_SKILLS):
    """Ticket id when this record invokes do-ticket (or a dispatcher skill) for a ticket, else None."""
    msg = rec.get('message') or {}
    content = msg.get('content')
    if rec.get('type') == 'assistant' and isinstance(content, list):
        for b in content:
            if b.get('type') == 'tool_use' and b.get('name') == 'Skill':
                inp = b.get('input') or {}
                if inp.get('skill') in run_skills:
                    m = TICKET.search(inp.get('args') or '')
                    if m:
                        return m.group(1)
    if rec.get('type') == 'user':
        for name, args in COMMAND.findall(user_text(rec)):
            if name in run_skills:
                m = TICKET.search(args or '')
                if m:
                    return m.group(1)
    return None


def brief_ticket(rec):
    """Ticket a child session's brief is about: the id it names most often (beats a stray 'UTF-8')."""
    text = user_text(rec) if rec.get('type') == 'user' else ''
    if CHILD_BRIEF not in text:
        return None
    ids = TICKET.findall(text.split(CHILD_BRIEF, 1)[1])
    return max(set(ids), key=ids.count) if ids else None


def marker(rec):
    """Part this record moves the run into, else None."""
    msg = rec.get('message') or {}
    content = msg.get('content')
    if rec.get('type') == 'assistant' and isinstance(content, list):
        for b in content:
            if b.get('type') != 'tool_use':
                continue
            inp = b.get('input') or {}
            if b.get('name') == 'Read':
                m = PHASE_FILE.search(inp.get('file_path') or '')
                if m and m.group(1).lower() in PARTS:
                    return m.group(1).lower()
            if b.get('name') == 'Skill' and inp.get('skill') in SKILL_PART:
                return SKILL_PART[inp['skill']]
            if b.get('name') in ('Bash', 'PowerShell'):
                cmd = inp.get('command') or ''
                m = PHASE_FILE.search(cmd)
                if m and m.group(1).lower() in PARTS:
                    return m.group(1).lower()
                for rx, part in COMMAND_PART:
                    if rx.search(cmd):
                        return part
    if rec.get('type') == 'user' and isinstance(content, str):
        for name, _ in COMMAND.findall(content):
            if name in SKILL_PART:
                return SKILL_PART[name]
    return None


class Book:
    def __init__(self):
        self.rows = defaultdict(lambda: defaultdict(float))   # (ticket, part, who) -> tokens + usd
        self.agents = defaultdict(lambda: defaultdict(float))  # (ticket, agent_type) -> usd, count
        self.sessions = defaultdict(set)
        self.first = {}
        self.active = defaultdict(float)
        self.seen = set()

    def add(self, ticket, part, who, usage, model, key):
        if key in self.seen:
            return
        self.seen.add(key)
        t, usd = cost(usage, model)
        r = self.rows[(ticket, part, who)]
        for k, v in t.items():
            r[k] += v
        r['usd'] += usd
        return usd


def scan_main(path, book, run_skills=RUN_SKILLS):
    """Walk one main transcript; return its timeline for sub-agent lookup."""
    ticket, part, last_t = None, None, None
    timeline = []  # (time, ticket, part)
    session = os.path.splitext(os.path.basename(path))[0]
    first_user = True
    for rec in records(path):
        t = ts(rec.get('timestamp'))
        new = invocation(rec, run_skills)
        if first_user and rec.get('type') == 'user' and user_text(rec).strip():
            first_user = False
            new = new or brief_ticket(rec)
        if new:
            if new != ticket:
                ticket, part = new, 'start'
            book.sessions[ticket].add(session)
            if t is not None:
                book.first[ticket] = min(book.first.get(ticket, t), t)
        if ticket:
            p = marker(rec)
            if p:
                part = p
            if t is not None:
                timeline.append((t, ticket, part))
                if last_t is not None and 0 < t - last_t <= GAP:
                    book.active[ticket] += t - last_t
                last_t = t
            msg = rec.get('message') or {}
            if rec.get('type') == 'assistant' and msg.get('usage'):
                key = msg.get('id') or rec.get('requestId') or rec.get('uuid')
                book.add(ticket, part, 'main', msg['usage'], msg.get('model'), key)
    return timeline


def scan_agents(path, timeline, book):
    if not timeline:
        return
    times = [x[0] for x in timeline]
    folder = os.path.join(os.path.splitext(path)[0], 'subagents')
    for f in glob.glob(os.path.join(folder, 'agent-*.jsonl')):
        meta = {}
        try:
            with open(f[:-len('.jsonl')] + '.meta.json', encoding='utf-8') as m:
                meta = json.load(m)
        except (OSError, ValueError):
            warnings['sub-agent with no .meta.json'].add(os.path.basename(f))
        kind = meta.get('agentType') or 'unknown'
        owner = None
        for rec in records(f):
            t = ts(rec.get('timestamp'))
            if owner is None and t is not None:
                i = bisect.bisect_right(times, t) - 1
                if i < 0:
                    break  # started before any ticket window
                owner = timeline[i]
                book.agents[(owner[1], kind)]['count'] += 1
            msg = rec.get('message') or {}
            if owner and rec.get('type') == 'assistant' and msg.get('usage'):
                key = msg.get('id') or rec.get('requestId') or rec.get('uuid')
                usd = book.add(owner[1], owner[2], 'sub', msg['usage'], msg.get('model'), key)
                if usd:
                    book.agents[(owner[1], kind)]['usd'] += usd


def scan(projects_dir, dispatchers=()):
    book = Book()
    run_skills = RUN_SKILLS + tuple(dispatchers)
    for path in sorted(glob.glob(os.path.join(projects_dir, '*', '*.jsonl'))):
        timeline = scan_main(path, book, run_skills)
        scan_agents(path, timeline, book)
    return book


def fmt_m(n):
    return f'{n / 1e6:.2f}M'


def report(book, ticket):
    parts = [p for p in PARTS if any((ticket, p, w) in book.rows for w in ('main', 'sub'))]
    if not parts:
        print(f'No do-ticket run found for {ticket}.', file=sys.stderr)
        return 1
    print(f'## {ticket} — cost from transcripts (prices as of {PRICES_AS_OF})\n')
    print('| Part | Main $ | Sub-agent $ | Total $ | Output | Cache write | Cache read |')
    print('|---|---|---|---|---|---|---|')
    tot = defaultdict(float)
    for p in parts:
        mn, sb = book.rows.get((ticket, p, 'main'), {}), book.rows.get((ticket, p, 'sub'), {})
        row = {k: mn.get(k, 0) + sb.get(k, 0) for k in ('usd', 'output', 'write', 'read', 'input')}
        for k, v in row.items():
            tot[k] += v
        tot['main'] += mn.get('usd', 0)
        tot['sub'] += sb.get('usd', 0)
        print(f"| {p} | {mn.get('usd', 0):.2f} | {sb.get('usd', 0):.2f} | {row['usd']:.2f} | "
              f"{fmt_m(row['output'])} | {fmt_m(row['write'])} | {fmt_m(row['read'])} |")
    print(f"| **Total** | {tot['main']:.2f} | {tot['sub']:.2f} | **{tot['usd']:.2f}** | "
          f"{fmt_m(tot['output'])} | {fmt_m(tot['write'])} | {fmt_m(tot['read'])} |")
    print(f"\nSessions: {len(book.sessions[ticket])} · active minutes: {book.active[ticket] / 60:.0f}")
    agents = sorted(((k[1], v) for k, v in book.agents.items() if k[0] == ticket), key=lambda x: -x[1]['usd'])
    if agents:
        print('Sub-agents: ' + ', '.join(f"{a} ×{int(v['count'])} ${v['usd']:.2f}" for a, v in agents))
    print('Note: a part is the last marker seen — the first lines after a marker may belong to the step before.')
    return 0


def listing(book, since):
    tickets = sorted(book.first, key=lambda t: book.first[t])
    if since:
        cut = ts(since + 'T00:00:00+00:00')
        tickets = [t for t in tickets if book.first[t] >= cut]
    if not tickets:
        print('No do-ticket run found.', file=sys.stderr)
        return 1
    print(f'| First seen | Ticket | Sessions | Active min | Main $ | Sub $ | Total $ |  (prices as of {PRICES_AS_OF})')
    print('|---|---|---|---|---|---|---|')
    for t in tickets:
        mn = sum(v['usd'] for k, v in book.rows.items() if k[0] == t and k[2] == 'main')
        sb = sum(v['usd'] for k, v in book.rows.items() if k[0] == t and k[2] == 'sub')
        day = datetime.fromtimestamp(book.first[t]).strftime('%Y-%m-%d')
        print(f'| {day} | {t} | {len(book.sessions[t])} | {book.active[t] / 60:.0f} | {mn:.2f} | {sb:.2f} | {mn + sb:.2f} |')
    return 0


def main(argv=None):
    # Windows consoles default to cp1252 and print the report's em dashes and multiply signs as U+FFFD.
    # Same fix as check_artifacts.py.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('ticket', nargs='?')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--since')
    ap.add_argument('--projects-dir', default=os.path.expanduser('~/.claude/projects'))
    ap.add_argument('--dispatcher-skill', action='append', default=[],
                    help='a skill that dispatches a ticket to other sessions; its invocation with a '
                         'ticket id opens a window like do-ticket does (repeatable)')
    a = ap.parse_args(argv)
    if not a.list and not a.ticket:
        ap.print_usage(sys.stderr)
        return 2
    if not os.path.isdir(a.projects_dir):
        print(f'No such folder: {a.projects_dir}', file=sys.stderr)
        return 2
    book = scan(a.projects_dir, a.dispatcher_skill)
    code = listing(book, a.since) if a.list else report(book, a.ticket)
    for kind, items in sorted(warnings.items()):
        print(f'warning: {kind}: {len(items)} — e.g. {sorted(items)[:3]}', file=sys.stderr)
    return code


if __name__ == '__main__':
    sys.exit(main())
