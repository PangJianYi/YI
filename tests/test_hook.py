"""Exercise YI through real Git indexes; no source-text assertions."""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'YI test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.write('app.py', 'answer = 1\n')
        self.git('add', 'app.py')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args],
                              capture_output=True, check=True).stdout

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def yi(self, action, code=0, *options):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/yi.py'),
                                 '-C', str(self.root), action, *options],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def config(self):
        return json.loads((self.root / '.ratchet.json').read_text())

    def baseline(self):
        self.yi('init')
        self.git('add', '.ratchet.json')
        self.git('commit', '-qm', 'initial baseline')

    def test_init_uses_staged_blobs_and_preserves_index(self):
        self.write('app.py', 'unstaged = 1\n' * 10)
        self.write('untracked.py', 'hidden = 1\n' * 500)
        index = self.git('ls-files', '--stage')
        self.yi('init')
        self.assertEqual(self.config()['ceilings']['source'], 1)
        self.assertEqual(index, self.git('ls-files', '--stage'))
        self.yi('init', 2)

    def test_growth_grant_cleanup_and_regrowth(self):
        self.baseline()
        self.write('app.py', 'answer = 1\nextra = 2\n')
        self.git('add', 'app.py')
        self.write('app.py', 'answer = 1\n')
        self.yi('check', 1)
        cfg = self.config()
        cfg['ceilings']['source'] = 2
        self.write('.ratchet.json', json.dumps(cfg))
        self.git('add', '.ratchet.json')
        self.yi('check', 1)  # Hand raising the ceiling is not a grant.
        cfg['ceilings']['source'] = 1
        self.write('.ratchet.json', json.dumps(cfg))
        subprocess.run([sys.executable, '-m', 'ratchet', '-C', str(self.root),
                        'grant', '+1', '--group', 'source', '--reason', 'test feature',
                        '--by', 'test'], check=True, capture_output=True)
        self.git('add', '.ratchet.json', '.ratchet-grants.jsonl')
        self.yi('check')
        self.git('commit', '-qm', 'feature and grant')
        self.git('add', 'app.py')
        self.write('untracked.py', 'ignored = 1\n' * 500)
        self.yi('tighten')
        self.assertEqual(self.config()['ceilings']['source'], 1)
        self.yi('tighten', 2)  # Updated policy is not staged yet.
        self.git('add', '.ratchet.json')
        self.yi('check')
        self.write('app.py', 'answer = 1\nextra = 2\n')
        self.git('add', 'app.py')
        self.yi('check', 1)

    def test_scope_change_is_explicit_and_baseline_cannot_be_recreated(self):
        self.baseline()
        cfg = self.config()
        cfg['groups']['source']['exclude'] = ['app.py']
        self.write('.ratchet.json', json.dumps(cfg))
        self.git('add', '.ratchet.json')
        self.yi('check', 2)
        self.yi('check', 0, '--accept-policy-change')
        digest = hashlib.sha256(json.dumps(list(cfg['groups'].items()), sort_keys=True,
                                           separators=(',', ':')).encode()).hexdigest()
        entry = {'target': 'scope:' + digest, 'lines': 0, 'scope_sha256': digest,
                 'reason': 'test scope approval', 'by': 'test'}
        self.write('.ratchet-grants.jsonl', json.dumps(entry) + '\n')
        self.git('add', '.ratchet-grants.jsonl')
        self.yi('check')
        cfg['groups']['source']['exclude'] = ['*.py']
        self.write('.ratchet.json', json.dumps(cfg))
        self.git('add', '.ratchet.json')
        self.yi('check', 2)  # A grant for a different scope cannot be reused.
        self.git('rm', '-f', '.ratchet.json')
        self.yi('check', 2)
        self.yi('init', 2)
        self.assertFalse((self.root / '.ratchet.json').exists())

    def test_docs_tests_and_unclassified_assets_are_visible(self):
        self.write('README.md', 'Purpose\nUsage\n')
        self.write('tests/test_app.py', 'assert True\n')
        self.write('data/input.csv', 'value\n1\n')
        self.git('add', '.')
        report = self.yi('init').stdout
        self.assertEqual(self.config()['ceilings']['docs'], 2)
        self.assertEqual(self.config()['ceilings']['tests'], 1)
        self.assertIn('data/input.csv', report)
        self.git('add', '.ratchet.json')
        self.write('README.md', 'Purpose\nUsage\nMore\n')
        self.git('add', 'README.md')
        self.yi('check', 1)

    def test_budgeted_links_and_lfs_pointers_are_rejected(self):
        self.baseline()
        (self.root / 'link.py').symlink_to('app.py')
        self.git('add', 'link.py')
        self.yi('check', 2)
        self.git('rm', '-f', 'link.py')
        self.write('app.py', 'version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 5\n')
        self.git('add', 'app.py')
        self.yi('check', 2)

    def test_hook_runs_the_shared_tool(self):
        self.baseline()
        destination = self.root / '.yi/yi.py'
        destination.parent.mkdir()
        shutil.copy2(ROOT / 'scripts/yi.py', destination)
        environment = self.root / '.cache/ratchet-env'
        environment.parent.mkdir()
        environment.symlink_to(sys.prefix, target_is_directory=True)
        result = subprocess.run([str(ROOT / 'templates/pre-commit')], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_init_never_follows_policy_symlink(self):
        external = self.root / 'not-created.json'
        (self.root / '.ratchet.json').symlink_to(external)
        self.yi('init', 2)
        self.assertFalse(external.exists())

    def test_plain_text_and_extensionless_hooks_are_budgeted(self):
        self.write('writing.txt', 'Clear facts\n')
        self.write('.githooks/pre-commit', '#!/bin/sh\nexit 0\n')
        self.write('templates/pre-commit', '#!/bin/sh\nexit 0\n')
        self.git('add', '.')
        self.yi('init')
        self.assertEqual(self.config()['ceilings']['docs'], 1)
        self.assertEqual(self.config()['ceilings']['maintenance'], 4)
        self.git('add', '.ratchet.json')
        self.write('writing.txt', 'Clear facts\nMore\n')
        self.git('add', 'writing.txt')
        self.yi('check', 1)

    def test_group_order_cannot_move_tests_into_source_allowance(self):
        self.write('tests/test_app.py', 'assert True\n')
        self.git('add', '.')
        self.yi('init')
        cfg = self.config()
        cfg['ceilings']['source'] = 3
        self.write('.ratchet.json', json.dumps(cfg))
        self.git('add', '.ratchet.json')
        self.git('commit', '-qm', 'baseline with deliberate source allowance')
        self.write('tests/test_app.py', 'assert True\nassert 1\n')
        self.git('add', 'tests/test_app.py')
        self.yi('check', 1)
        cfg['groups'] = {'source': cfg['groups']['source'],
                         **{g: v for g, v in cfg['groups'].items() if g != 'source'}}
        self.write('.ratchet.json', json.dumps(cfg))
        self.git('add', '.ratchet.json')
        self.yi('check', 2)

    def test_stdout_is_one_json_report_for_all_successful_actions(self):
        for action in ['init', 'budget', 'check', 'tighten']:
            if action != 'init':
                self.git('add', '.ratchet.json')
            report = json.loads(self.yi(action).stdout)
            self.assertEqual(report['groups']['source']['lines'], 1)
