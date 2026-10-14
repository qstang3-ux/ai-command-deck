"""Install the skill using the current Python environment; back up prior skill."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

if importlib.util.find_spec('ai_command_deck') is None or importlib.util.find_spec('aiohttp') is None:
    sys.exit('Install this project with this Python first: python -m pip install .')
source = Path(__file__).resolve().parents[1] / 'skill/server-terminal-viewer'
target = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'skills/server-terminal-viewer'
if target.exists():
    backup = target.parent.parent / 'skill-backups' / ('server-terminal-viewer-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(backup))
    print(f'Previous skill backed up: {backup}')
shutil.copytree(source, target)
(target / 'scripts/runtime.json').write_text(json.dumps({'python': sys.executable}))
print(f'Installed: {target}')
