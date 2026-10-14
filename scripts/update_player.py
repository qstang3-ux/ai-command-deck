"""Refresh the pinned official player, verifying npm's SHA-512 integrity."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

VERSION='3.17.0'
with urllib.request.urlopen(f'https://registry.npmjs.org/asciinema-player/{VERSION}',timeout=30) as response:
    package=json.load(response)
with urllib.request.urlopen(package['dist']['tarball'],timeout=60) as response:
    data=response.read()
algorithm,digest=package['dist']['integrity'].split('-',1)
if algorithm!='sha512' or base64.b64encode(hashlib.sha512(data).digest()).decode()!=digest:
    raise SystemExit('Package integrity check failed')
destination=Path(__file__).resolve().parents[1]/'ai_command_deck/static/vendor'
destination.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    for member,target in [('package/dist/bundle/asciinema-player.min.js','asciinema-player.min.js'),('package/dist/bundle/asciinema-player.css','asciinema-player.css'),('package/LICENSE','LICENSE')]:
        (destination/target).write_bytes(archive.extractfile(member).read())
print(f'Bundled official asciinema-player {VERSION}; SHA-512 verified.')
