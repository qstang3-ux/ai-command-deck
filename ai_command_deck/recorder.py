"""Record a real PTY as asciicast v2, retaining output and resize timing."""
import codecs
import errno
import fcntl
import json
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
import tty
import uuid
from .storage import utcnow


def terminal_size():
    try:
        rows, cols, _, _ = struct.unpack("HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8))
        return (cols or 100, rows or 30)
    except (OSError, ValueError):
        return (100, 30)


def record(store, command, name=None):
    store.cleanup()
    ident = uuid.uuid4().hex
    meta = dict(id=ident, name=name or os.path.basename(command[0]), created=utcnow(), pid=os.getpid())
    store.save(meta)
    started = time.monotonic()
    # Open privately from creation, never temporarily world-readable.
    def private(path, flags):
        return os.open(path, flags, 0o600)
    with open(store.file(ident, ".log"), "wb", buffering=0, opener=private) as log, open(store.file(ident, ".cast"), "w", buffering=1, encoding="utf-8", opener=private) as cast:
        cols, rows = terminal_size()
        cast.write(json.dumps(dict(version=2, width=cols, height=rows, timestamp=int(time.time()), title=meta["name"], env={"TERM": os.environ.get("TERM", "xterm-256color")}), ensure_ascii=False) + "\n")
        def event(kind, data):
            cast.write(json.dumps([round(time.monotonic() - started, 6), kind, data], ensure_ascii=False) + "\n")
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.environ.setdefault("TERM", "xterm-256color")
                os.execvp(command[0], command)
            except OSError as exc:
                os.write(2, (str(exc) + "\n").encode())
                os._exit(127)
        old = None
        resized = False
        interrupted = False
        def on_resize(*_):
            nonlocal resized
            resized = True
        def on_stop(*_):
            nonlocal interrupted
            interrupted = True
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGWINCH, signal.SIGTERM, signal.SIGINT)}
        signal.signal(signal.SIGWINCH, on_resize)
        signal.signal(signal.SIGTERM, on_stop)
        signal.signal(signal.SIGINT, on_stop)
        def apply_size(log_event=False):
            w, h = terminal_size()
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", h, w, 0, 0))
            if log_event:
                event("r", f"{w}x{h}")
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        status = 0
        input_open = True
        try:
            apply_size()
            if sys.stdin.isatty():
                old = termios.tcgetattr(0)
                tty.setraw(0)
            while True:
                if interrupted:
                    os.kill(pid, signal.SIGHUP)
                    interrupted = False
                if resized:
                    apply_size(True)
                    resized = False
                ready, _, _ = select.select([fd] + ([0] if input_open else []), [], [], 0.1)
                if fd in ready:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    log.write(chunk)
                    text = decoder.decode(chunk)
                    if text:
                        event("o", text)
                    os.write(1, chunk)
                if input_open and 0 in ready:
                    chunk = os.read(0, 65536)
                    if chunk:
                        os.write(fd, chunk)  # Input is forwarded, never recorded.
                    else:
                        input_open = False
                        os.write(fd, b"\x04")
        finally:
            if old is not None:
                termios.tcsetattr(0, termios.TCSADRAIN, old)
            os.close(fd)
            _, status = os.waitpid(pid, 0)
            tail = decoder.decode(b"", final=True)
            if tail:
                event("o", tail)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            meta.update(ended=utcnow(), duration=round(time.monotonic()-started, 3), exit_code=os.waitstatus_to_exitcode(status))
            store.save(meta)
    return meta["exit_code"] if meta["exit_code"] >= 0 else 128 - meta["exit_code"]
