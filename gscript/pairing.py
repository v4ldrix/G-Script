"""One-time 6-digit pairing codes."""
import hmac
import secrets
import threading
import time
from pathlib import Path


class PairCode:
    """Code the user types to receive a token. Rotates after use or 5 wrong tries."""

    def __init__(self, on_rotate=None):
        self.on_rotate = on_rotate
        self.code = ""
        self.fails = 0
        self._lock = threading.Lock()
        self._rotate(announce=False)

    def _rotate(self, announce=True):
        self.code = f"{secrets.randbelow(10**6):06d}"
        self.fails = 0
        if announce and self.on_rotate:
            self.on_rotate(self.code)

    def rotate(self):
        with self._lock:
            self._rotate()

    def try_code(self, attempt):
        with self._lock:
            if hmac.compare_digest(str(attempt).encode(), self.code.encode()):
                self._rotate()
                return True
            self.fails += 1
            if self.fails >= 5:
                self._rotate()
            return False


class ExtTrust:
    """Browser-extension pairing without codes. The first extension to ask is trusted (and remembered);
    another one can only take over after the first has been silent for `idle` seconds or was forgotten."""

    def __init__(self, path=None, idle=60.0, on_event=None):
        self.path = Path(path) if path else None
        self.idle, self.on_event = idle, on_event
        self._lock = threading.Lock()
        self.pinned = ""
        try:
            if self.path and self.path.exists():
                self.pinned = self.path.read_text().strip()
        except OSError:
            pass
        self.seen = time.time() if self.pinned else 0.0   # grace period after a restart

    def _pin(self, origin):
        changed = origin != self.pinned
        self.pinned, self.seen = origin, time.time()
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(origin)
            except OSError:
                pass
        if changed and self.on_event:
            self.on_event("Browser extension connected")

    def allow(self, origin):
        if not str(origin).startswith(("chrome-extension://", "moz-extension://")):
            return False
        with self._lock:
            if not self.pinned or self.pinned == origin or time.time() - self.seen > self.idle:
                self._pin(origin)
                return True
            return False

    def touch(self, origin):
        if origin and origin == self.pinned:
            self.seen = time.time()

    def forget(self):
        with self._lock:
            self.pinned, self.seen = "", 0.0
            if self.path:
                try:
                    self.path.unlink()
                except OSError:
                    pass
