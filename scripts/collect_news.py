"""Run broad public discovery, using the current user's local priority list when present."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--hours', type=int, choices=(12, 24, 48, 72, 96), default=24)
    parser.add_argument('--as-of')
    parser.add_argument('--priority-file', type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        raise ValueError('Workspace must be an existing directory')
    project = next((p for p in (workspace / 'morning-note', workspace)
                    if (p / 'morning_note.py').is_file() and (p / 'config.json').is_file()), None)
    if project is not None and args.priority_file is None:
        collector = project / 'morning_note.py'
        config = project / 'config.json'
    else:
        collector = ROOT / 'collector' / 'morning_note.py'
        run = workspace / 'morning-note-runs' / ('collection-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        run.mkdir(parents=True, exist_ok=False)
        defaults = json.loads((ROOT / 'collector' / 'config.json').read_text(encoding='utf-8'))
        priorities = json.loads(args.priority_file.read_text(encoding='utf-8-sig')) if args.priority_file else []
        if not isinstance(priorities, list):
            raise ValueError('Priority file must be a JSON list')
        (run / 'watchlist.json').write_text(json.dumps(priorities, ensure_ascii=False, indent=2), encoding='utf-8')
        (run / 'inbox.json').write_text('[]', encoding='utf-8')
        config = run / 'config.json'
        config.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding='utf-8')
    command = [sys.executable, str(collector), 'run', '--config', str(config), '--mode', 'market-first', '--hours', str(args.hours), '--dry-run']
    if args.as_of:
        command += ['--as-of', args.as_of]
    result = subprocess.run(command, cwd=str(workspace), check=False)
    return result.returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print('Collection could not start: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
