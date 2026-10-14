"""Private local session storage; no recordings are placed in the source tree."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import time

ID = re.compile(r"^[a-f0-9]{32}$")


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def active(meta):
    if meta.get("ended"):
        return False
    try:
        os.kill(int(meta["pid"]), 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, KeyError, ValueError, TypeError):
        return True  # If unsure, never remove a potentially running session.


class Store:
    def __init__(self, directory=None, retention_days=None):
        self.path = Path(directory or os.environ.get("TERMINAL_VIEWER_DATA", Path.home() / ".codex/terminal-viewer/sessions")).expanduser()
        self.days = int(retention_days if retention_days is not None else os.environ.get("TERMINAL_VIEWER_RETENTION_DAYS", "7"))
        if self.days < 1:
            raise ValueError("retention days must be at least 1")
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.chmod(0o700)

    def file(self, ident, suffix):
        if not ID.fullmatch(ident):
            raise ValueError("invalid session id")
        return self.path / (ident + suffix)

    def save(self, meta):
        target = self.file(meta["id"], ".json")
        tmp = target.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)) as out:
            json.dump(meta, out, ensure_ascii=False)
        os.replace(tmp, target)

    def read(self, ident):
        return json.loads(self.file(ident, ".json").read_text())

    def sessions(self):
        result = []
        for path in self.path.glob("*.json"):
            if not ID.fullmatch(path.stem):
                continue
            try:
                meta = self.read(path.stem)
                dt.datetime.fromisoformat(meta["created"])
                # Whitelist fields rather than expose arbitrary metadata to the browser.
                item = {key: meta[key] for key in ("name", "created", "ended", "duration", "exit_code") if key in meta}
                item.update(id=path.stem, active=active(meta), recording=self.file(path.stem, ".cast").is_file())
                result.append(item)
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda x: dt.datetime.fromisoformat(x["created"]).timestamp(), reverse=True)

    def cleanup(self, now=None):
        cutoff = (time.time() if now is None else now) - self.days * 86400
        removed = []
        for path in self.path.glob("*.json"):
            if not ID.fullmatch(path.stem):
                continue
            try:
                meta = self.read(path.stem)
                if active(meta):
                    continue
                files = [self.file(path.stem, suffix) for suffix in (".log", ".cast", ".json")]
                stamp = dt.datetime.fromisoformat(meta["ended"]).timestamp() if meta.get("ended") else max(p.stat().st_mtime for p in files if p.exists())
                if stamp > cutoff:
                    continue
                for item in files:
                    item.unlink(missing_ok=True)
                removed.append(path.stem)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return removed
