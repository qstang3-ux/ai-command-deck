#!/usr/bin/env python3
"""Compatibility entry point installed with the reusable skill."""
import json
import os
from pathlib import Path
import sys

config = Path(__file__).with_name('runtime.json')
runtime = json.loads(config.read_text())['python'] if config.exists() else sys.executable
if not Path(runtime).is_file():
    sys.exit('AI Command Deck runtime missing. Reinstall the skill using scripts/install_skill.py.')
os.execv(runtime, [runtime, '-m', 'ai_command_deck', *sys.argv[1:]])
