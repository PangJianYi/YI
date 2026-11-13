#!/usr/bin/env python3
"""Install persistent project guidance and a chained Git hook; never stage files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

START, END = '<!-- YI:BEGIN -->', '<!-- YI:END -->'
SOURCE = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def locate(project):
    root = Path(git(project, 'rev-parse', '--show-toplevel'))
    if not (root / '.git').is_dir() or (root / '.git').is_symlink():
        raise ValueError('Activation currently supports ordinary Git checkouts, not linked worktrees')
    hook = Path(git(root, 'rev-parse', '--git-path', 'hooks/pre-commit'))
    hook = hook if hook.is_absolute() else root / hook
    if not hook.parent.resolve().is_relative_to(root):
        raise ValueError('Shared external hooksPath: integrate the YI hook there explicitly')
    return root, hook, root / '.git/yi-resident.json'


def inspect(root, hook, state_path):
    if not state_path.exists():
        return {'enabled': False, 'ready': False}
    state = json.loads(state_path.read_text())
    problems = []
    for name, record in state['files'].items():
        p = root / name
        if p.is_symlink() or not p.is_file():
            problems.append(name + ': missing or linked')
        elif record['kind'] == 'rules':
            if p.read_text().count(state['block']) != 1:
                problems.append(name + ': managed rules changed')
        elif digest(p.read_bytes()) != record['sha256']:
            problems.append(name + ': installed tool changed')
    if hook.is_symlink() or not hook.exists() or digest(hook.read_bytes()) != state['hook_sha256']:
        problems.append('pre-commit hook changed')
    backup = hook.with_name('pre-commit.yi-original')
    if state['original_hook'] and not os.access(backup, os.X_OK):
        problems.append('original pre-commit backup missing or not executable')
    if hook.exists() and not os.access(hook, os.X_OK):
        problems.append('pre-commit hook is not executable')
    if 'AGENTS.md' in state['files'] and (root / 'AGENTS.override.md').exists():
        problems.append('AGENTS.override.md now shadows the managed AGENTS.md')
    python = root / '.cache/ratchet-env/bin/python'
    probe = subprocess.run([str(python), '-c',
                            'import importlib.metadata; print(importlib.metadata.version("ratchet-size"))'],
                           capture_output=True, text=True) if python.is_file() else None
    if probe is None or probe.returncode or probe.stdout.strip() != '0.2.3':
        problems.append('project Ratchet 0.2.3 environment missing')
    if not subprocess.run(['git', '-C', str(root), 'cat-file', '-e', ':.ratchet.json'],
                          capture_output=True).returncode == 0:
        problems.append('stage .ratchet.json to activate commit checks')
    return {'enabled': True, 'ready': not problems, 'problems': problems,
            'rules': [p for p, v in state['files'].items() if v['kind'] == 'rules'],
            'new_session_required': True, 'semantic_compliance': 'agent instructions, not mechanically enforced'}


def enable(root, hook, state_path):
    if state_path.exists():
        return inspect(root, hook, state_path)
    python = root / '.cache/ratchet-env/bin/python'
    if not python.is_file():
        raise ValueError('Create .cache/ratchet-env and install ratchet-size==0.2.3 first')
    result = subprocess.run([str(python), '-c',
                             'import importlib.metadata; print(importlib.metadata.version("ratchet-size"))'],
                            capture_output=True, text=True)
    if result.returncode or result.stdout.strip() != '0.2.3':
        raise ValueError('Project environment must contain ratchet-size==0.2.3')
    tool = root / '.yi/yi.py'
    payload = (SOURCE / 'scripts/yi.py').read_bytes()
    if tool.parent.is_symlink() or tool.is_symlink() or (tool.exists() and tool.read_bytes() != payload):
        raise ValueError('Existing .yi/yi.py differs; reconcile it before activation; nothing overwritten')
    tool_existed = tool.exists()
    rules = ['AGENTS.override.md' if (root / 'AGENTS.override.md').exists() else 'AGENTS.md']
    if (root / 'CLAUDE.md').exists():
        rules.append('CLAUDE.md')
    block = '\n\n' + START + '\n' + (SOURCE / 'templates/AGENTS.md').read_text().strip() + '\n' + END + '\n'
    before = {}
    for name in rules:
        p = root / name
        if p.is_symlink():
            raise ValueError(name + ': linked rule files require explicit integration')
        text = p.read_text() if p.exists() else None
        remainder = (text or '').replace(block, '', 1)
        if START in remainder or END in remainder:
            raise ValueError(name + ': unmanaged YI markers already exist')
        before[name] = text
    backup = hook.with_name('pre-commit.yi-original')
    if backup.exists() or backup.is_symlink():
        raise ValueError('Existing hook backup; reconcile before enabling')
    original = hook.exists() or hook.is_symlink()
    if original and not os.access(hook, os.X_OK):
        raise ValueError('Existing hook is not executable; reconcile before enabling')
    wrapper = '''#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
backup=$(git rev-parse --git-path hooks/pre-commit.yi-original)
if [ -x "$backup" ]; then "$backup" "$@"; fi
exec "$root/.cache/ratchet-env/bin/python" "$root/.yi/yi.py" -C "$root" check
'''
    files = {name: {'kind': 'rules', 'created': text is None} for name, text in before.items()}
    files['.yi/yi.py'] = {'kind': 'tool', 'sha256': digest(payload)}
    try:
        tool.parent.mkdir(exist_ok=True)
        tool.write_bytes(payload)
        for name, text in before.items():
            if block not in (text or ''):
                (root / name).write_text((text or '') + block)
        hook.parent.mkdir(parents=True, exist_ok=True)
        if original:
            hook.rename(backup)
        hook.write_text(wrapper)
        hook.chmod(0o755)
        state_path.write_text(json.dumps({'files': files, 'block': block,
                                         'hook_sha256': digest(wrapper.encode()),
                                         'original_hook': original}, ensure_ascii=False, indent=2) + '\n')
    except Exception:
        for name, text in before.items():
            if text is None:
                (root / name).unlink(missing_ok=True)
            else:
                (root / name).write_text(text)
        if not tool_existed:
            tool.unlink(missing_ok=True)
        if backup.exists() or backup.is_symlink():
            hook.unlink(missing_ok=True)
            backup.rename(hook)
        elif not original:
            hook.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)
        raise
    return inspect(root, hook, state_path)


def disable(root, hook, state_path):
    if not state_path.exists():
        return {'enabled': False, 'ready': False}
    state = json.loads(state_path.read_text())
    # Validate every managed edit before removing any of them.
    problems = inspect(root, hook, state_path)['problems']
    protected = [p for p in problems if p not in (
        'project Ratchet 0.2.3 environment missing', 'stage .ratchet.json to activate commit checks')]
    if protected:
        raise ValueError('Preserving modified installation: ' + '; '.join(protected))
    backup = hook.with_name('pre-commit.yi-original')
    if state['original_hook'] and not (backup.exists() or backup.is_symlink()):
        raise ValueError('Original hook backup missing; refusing partial uninstall')
    for name, record in state['files'].items():
        p = root / name
        if record['kind'] == 'rules':
            text = p.read_text().replace(state['block'], '', 1)
            if record['created'] and not text:
                p.unlink()
            else:
                p.write_text(text)
        else:
            p.unlink()
    hook.unlink()
    if state['original_hook']:
        backup.rename(hook)
    state_path.unlink()
    if not any((root / '.yi').iterdir()):
        (root / '.yi').rmdir()
    return {'enabled': False, 'ready': False, 'retained': ['budget policy and grants', 'project environment']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'status', 'disable'])
    parser.add_argument('-C', '--project', default='.')
    args = parser.parse_args()
    try:
        root, hook, state = locate(args.project)
        result = {'enable': enable, 'status': inspect, 'disable': disable}[args.action](root, hook, state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.action == 'disable' or result.get('ready') else 1
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('yi resident: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
