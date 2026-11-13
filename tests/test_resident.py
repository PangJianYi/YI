"""Persistent activation uses actual hooks and preserves existing project state."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        env = self.root / '.cache/ratchet-env'
        env.parent.mkdir()
        env.symlink_to(sys.prefix, target_is_directory=True)
        (self.root / '.gitignore').write_text('.cache/\n')
        (self.root / 'app.py').write_text('answer = 1\n')
        self.git('add', '.gitignore', 'app.py')

    def git(self, *args, code=0):
        p = subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stderr + p.stdout)
        return p.stdout

    def resident(self, action, code=0):
        p = subprocess.run([sys.executable, str(ROOT / 'scripts/resident.py'), action,
                            '-C', str(self.root)], capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stderr + p.stdout)
        return json.loads(p.stdout) if p.stdout else None

    def prepare(self):
        self.resident('enable', 1)  # Installed, baseline still needs explicit staging.
        self.git('add', 'AGENTS.md', '.yi/yi.py')
        subprocess.run([sys.executable, str(self.root / '.yi/yi.py'), '-C', str(self.root),
                        'init'], check=True, capture_output=True)
        self.git('add', '.ratchet.json')
        self.assertTrue(self.resident('status')['ready'])

    def test_real_commits_stay_guarded_and_activation_is_idempotent(self):
        rules = self.root / 'AGENTS.md'
        rules.write_text('# Existing project rules\n')
        old = self.root / '.git/hooks/pre-commit'
        old.write_text('#!/bin/sh\necho previous-hook >&2\n')
        old.chmod(0o755)
        self.prepare()
        first = rules.read_bytes()
        self.resident('enable')
        self.assertEqual(first, rules.read_bytes())
        self.git('commit', '-qm', 'baseline')
        (self.root / 'app.py').write_text('answer = 1\nextra = 2\n')
        self.git('add', 'app.py')
        p = subprocess.run(['git', '-C', str(self.root), 'commit', '-qm', 'growth'],
                           capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('previous-hook', p.stderr)
        rules.write_text(rules.read_text() + '\nUser addition\n')
        self.resident('disable')
        self.assertEqual(rules.read_text(), '# Existing project rules\n\nUser addition\n')
        self.assertEqual(old.read_text(), '#!/bin/sh\necho previous-hook >&2\n')
        self.assertTrue((self.root / '.ratchet.json').exists())

    def test_modified_tool_is_preserved_on_disable(self):
        self.prepare()
        tool = self.root / '.yi/yi.py'
        tool.write_text(tool.read_text() + '\n# user modification\n')
        self.resident('status', 1)
        self.resident('disable', 2)
        self.assertTrue(tool.exists())
        self.assertTrue((self.root / '.git/hooks/pre-commit').exists())

    def test_rules_symlink_rejected_before_writes(self):
        (self.root / 'AGENTS.md').symlink_to('other.md')
        self.resident('enable', 2)
        self.assertFalse((self.root / '.yi').exists())
        self.assertFalse((self.root / '.git/hooks/pre-commit').exists())

    def test_override_and_existing_claude_rules_are_updated(self):
        for name in ('AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md'):
            (self.root / name).write_text('# ' + name + '\n')
        self.resident('enable', 1)
        self.assertNotIn('YI:BEGIN', (self.root / 'AGENTS.md').read_text())
        for name in ('AGENTS.override.md', 'CLAUDE.md'):
            self.assertIn('YI:BEGIN', (self.root / name).read_text())
        self.resident('disable')
        for name in ('AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md'):
            self.assertEqual((self.root / name).read_text(), '# ' + name + '\n')

    def test_new_checkout_can_reactivate_tracked_installation(self):
        self.prepare()
        self.git('commit', '-qm', 'baseline')
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / 'clone'
            subprocess.run(['git', 'clone', '-q', str(self.root), str(clone)], check=True)
            original = self.root
            self.root = clone
            env = clone / '.cache/ratchet-env'
            env.parent.mkdir()
            env.symlink_to(sys.prefix, target_is_directory=True)
            self.assertFalse(self.resident('status', 1)['enabled'])
            self.resident('enable')
            self.assertEqual((clone / 'AGENTS.md').read_text().count('YI:BEGIN'), 1)
            self.resident('disable')
            self.root = original

    def test_existing_hook_symlink_is_restored(self):
        script = self.root / 'original-check.sh'
        script.write_text('#!/bin/sh\nexit 0\n')
        script.chmod(0o755)
        hook = self.root / '.git/hooks/pre-commit'
        hook.symlink_to('../../original-check.sh')
        self.prepare()
        self.resident('disable')
        self.assertTrue(hook.is_symlink())
        self.assertEqual(hook.resolve(), script)

    def test_new_override_is_reported(self):
        self.prepare()
        (self.root / 'AGENTS.override.md').write_text('New overriding instructions\n')
        result = self.resident('status', 1)
        self.assertIn('AGENTS.override.md now shadows the managed AGENTS.md', result['problems'])
