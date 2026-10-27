"""Tests for ticket_cost.py on hand-made transcripts.  Run: python test_ticket_cost.py"""
import io, json, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ticket_cost as tc

T0 = '2026-10-01T10:00:%02dZ'


def asst(sec, msg_id, usage, model='claude-opus-5-5', tool=None):
    content = [{'type': 'tool_use', 'id': 'tu' + msg_id, 'name': tool[0], 'input': tool[1]}] if tool else []
    return {'type': 'assistant', 'timestamp': T0 % sec,
            'message': {'id': msg_id, 'model': model, 'usage': usage, 'content': content}}


def user(sec, text):
    return {'type': 'user', 'timestamp': T0 % sec, 'message': {'role': 'user', 'content': text}}


U = {'input_tokens': 1_000_000, 'output_tokens': 0, 'cache_read_input_tokens': 0,
     'cache_creation_input_tokens': 0, 'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0}}


def write(folder, name, recs):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r) + '\n')


class TicketCostTest(unittest.TestCase):
    def setUp(self):
        tc.warnings.clear()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        proj = os.path.join(self.dir, 'proj')
        write(proj, 's1.jsonl', [
            asst(0, 'pre', U),                                          # before any invocation: not counted
            user(1, '<command-name>/do-ticket</command-name>\n<command-args>PROJ-1 --worktree</command-args>'),
            asst(2, 'm1', U),                                           # start
            asst(3, 'm1', U),                                           # same message id: counted once
            asst(4, 'm2', U, tool=('Read', {'file_path': '/x/do-ticket/phases/design.md'})),   # -> design
            asst(5, 'm3', U, tool=('Read', {'file_path': r'C:\x\do-ticket\phases\build.md'})),  # -> build
            asst(6, 'm4', U, tool=('Skill', {'skill': 'do-ticket', 'args': 'PROJ-2'})),     # new ticket
            asst(7, 'm5', U, model='claude-unknown-9'),
        ])
        sub = os.path.join(proj, 's1', 'subagents')
        write(sub, 'agent-a.jsonl', [asst(5, 'a1', U, model='claude-sonnet-5-5')])
        with open(os.path.join(sub, 'agent-a.meta.json'), 'w') as f:
            json.dump({'agentType': 'Explore'}, f)
        self.book = tc.scan(self.dir)

    def usd(self, ticket, part, who, book=None):
        return round((book or self.book).rows.get((ticket, part, who), {}).get('usd', 0), 6)

    def test_window_and_dedup(self):
        self.assertEqual(self.usd('PROJ-1', 'start', 'main'), 4.0)   # m1 once, 1M input at $4
        self.assertNotIn('pre', [k for k in self.book.rows if k[0] is None])

    def test_shell_commands_are_part_markers(self):
        def rec(tool, cmd):
            return asst(1, 'x', U, tool=(tool, {'command': cmd}))
        self.assertEqual(tc.marker(rec('Bash', "sed -n '1,40p' ~/.claude/skills/do-ticket/phases/verify.md")), 'verify')
        self.assertEqual(tc.marker(rec('PowerShell', '& ~/.claude/skills/push-code/sonar-local.ps1 -Repo api')), 'verify')
        self.assertEqual(tc.marker(rec('Bash', 'python check_artifacts.py ~/t/PROJ-1 pre-push --type crud-feature')), 'verify')
        self.assertEqual(tc.marker(rec('Bash', 'gh pr create --base main --title x')), 'ship')
        self.assertIsNone(tc.marker(rec('Bash', 'git status --porcelain')))
        self.assertIsNone(tc.marker(rec('Bash', 'python check_artifacts.py ~/t/PROJ-1 done')))

    def test_part_markers(self):
        self.assertEqual(self.usd('PROJ-1', 'design', 'main'), 4.0)
        self.assertEqual(self.usd('PROJ-1', 'build', 'main'), 4.0)
        skill = asst(1, 'y', U, tool=('Skill', {'skill': 'enrich-requirements'}))
        self.assertEqual(tc.marker(skill), 'analyze')

    def test_subagent_booked_to_active_part(self):
        self.assertEqual(self.usd('PROJ-1', 'build', 'sub'), 2.0)    # sonnet 5.5 input $2
        self.assertEqual(int(self.book.agents[('PROJ-1', 'Explore')]['count']), 1)

    def test_new_ticket_and_unknown_model(self):
        self.assertEqual(self.usd('PROJ-2', 'start', 'main'), 4.0)
        self.assertIn('claude-unknown-9', tc.warnings['model not priced ($0)'])

    def test_cache_write_prices(self):
        u = dict(U, input_tokens=0, cache_creation_input_tokens=2_000_000,
                 cache_creation={'ephemeral_5m_input_tokens': 1_000_000, 'ephemeral_1h_input_tokens': 1_000_000})
        self.assertAlmostEqual(tc.cost(u, 'claude-opus-5-5')[1], 4 * 1.25 + 4 * 2)
        fast = dict(U, speed='fast')
        self.assertAlmostEqual(tc.cost(fast, 'claude-opus-5-5')[1], 8.0)

    def test_dispatcher_and_child_sessions_count(self):
        proj = os.path.join(self.dir, 'proj2')
        write(proj, 'dispatch.jsonl', [
            user(1, '<command-name>/dispatch</command-name>\n<command-args>do https://x/browse/PROJ-7 now</command-args>'),
            asst(2, 'r1', U),
        ])
        write(proj, 'child.jsonl', [
            user(1, '<system-reminder>\nLinked sessions now: a (idle)\n</system-reminder>\n\n'
                    'Background (from the session that started this one):\nWork on PROJ-7. Keep UTF-8. '
                    'Task:\nGoal: part 2 of PROJ-7'),
            asst(2, 'c1', U),
        ])
        write(proj, 'plain.jsonl', [user(1, 'hello PROJ-9'), asst(2, 'p1', U),
                                    user(3, 'Background (from the session that started this one): PROJ-9')])
        # Without --dispatcher-skill the dispatcher session is not a ticket window; the child still is.
        book = tc.scan(self.dir)
        self.assertEqual(book.sessions['PROJ-7'], {'child'})
        book = tc.scan(self.dir, dispatchers=('dispatch',))
        self.assertEqual(round(sum(v['usd'] for k, v in book.rows.items() if k[0] == 'PROJ-7'), 6), 8.0)
        self.assertEqual(book.sessions['PROJ-7'], {'dispatch', 'child'})
        self.assertNotIn('PROJ-9', book.first)    # the brief line only counts in the first user message
        self.assertNotIn('UTF-8', book.first)

    def test_missing_ticket_exits_1(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(tc.main(['PROJ-404', '--projects-dir', self.dir]), 1)

    def test_report_prints_for_a_found_ticket(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(tc.main(['PROJ-1', '--projects-dir', self.dir]), 0)
        self.assertIn('| build |', out.getvalue())


if __name__ == '__main__':
    result = unittest.main(exit=False, verbosity=1).result
    if result.testsRun == 0:   # a suite that ran nothing is not a pass
        sys.exit(2)
    sys.exit(0 if result.wasSuccessful() else 1)
