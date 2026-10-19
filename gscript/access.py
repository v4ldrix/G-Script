"""Pairing helpers for the phone: one-time secrets, rate limits and approve-on-the-PC requests."""
import re
import secrets
import threading
import time

ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"   # no look-alike characters (0/O, 1/I/L, U)


def new_secret(n=12):
    """Long one-time secret that goes into the QR code link (60 bits)."""
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def norm_secret(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


class PairLimiter:
    """After too many wrong pairing tries, refuse everything for a while (stops brute force)."""

    def __init__(self, max_fails=5, window=600.0):
        self.max_fails, self.window = max_fails, window
        self.fails = []
        self._lock = threading.Lock()

    def locked_for(self):
        with self._lock:
            now = time.time()
            self.fails = [t for t in self.fails if now - t < self.window]
            if len(self.fails) >= self.max_fails:
                return max(1, int(self.window - (now - self.fails[0])))
            return 0

    def fail(self):
        with self._lock:
            self.fails.append(time.time())

    def ok(self):
        with self._lock:
            self.fails.clear()


# ---------------- phone pairing by approval (no codes) ----------------
WORDS_A = ["BLUE", "RED", "GREEN", "GOLD", "PINK", "GRAY", "TEAL", "LIME", "PLUM", "SAND", "JADE", "RUBY", "COOL", "WARM",
           "FAST", "CALM", "BOLD", "KIND", "WILD", "SOFT", "BRAVE", "QUICK", "SUNNY", "LUCKY"]
WORDS_B = ["FOX", "OWL", "BEAR", "WOLF", "LION", "HAWK", "DEER", "SEAL", "CRAB", "MOTH", "LYNX", "KOI", "BAT", "EEL",
           "ANT", "YAK", "EMU", "ORCA", "TOAD", "WREN", "PANDA", "OTTER", "TIGER", "RAVEN"]


class KeyedLimiter:
    """At most `max_events` per key (e.g. per IP address) in `window` seconds."""

    def __init__(self, max_events=8, window=600.0):
        self.max_events, self.window = max_events, window
        self.events = {}
        self._lock = threading.Lock()

    def hit(self, key):
        with self._lock:
            now = time.time()
            recent = [t for t in self.events.get(key, []) if now - t < self.window]
            if len(recent) >= self.max_events:
                self.events[key] = recent
                return False
            recent.append(now)
            self.events[key] = recent
            return True


class PairRequests:
    """A phone asks to connect; the person at the PC compares the two words and clicks Allow."""

    def __init__(self, ttl=120.0, max_pending=3):
        self.ttl, self.max_pending = ttl, max_pending
        self.items = {}
        self._lock = threading.Lock()

    def _prune(self):
        now = time.time()
        for i in list(self.items):
            it = self.items[i]
            if now - it["t"] > self.ttl and it["status"] == "pending":
                it["status"] = "expired"
            if now - it["t"] > self.ttl * 3:
                del self.items[i]

    def create(self, ua, ip):
        with self._lock:
            self._prune()
            if sum(1 for it in self.items.values() if it["status"] == "pending") >= self.max_pending:
                return None
            clean = "".join(ch for ch in str(ua) if ch.isprintable())[:80]
            it = {"id": secrets.token_hex(8), "words": f"{secrets.choice(WORDS_A)} {secrets.choice(WORDS_B)}",
                  "ua": clean, "ip": str(ip)[:45], "t": time.time(), "status": "pending", "token": None}
            self.items[it["id"]] = it
            return dict(it)

    def pending(self):
        with self._lock:
            self._prune()
            now = time.time()
            return [{"id": i["id"], "words": i["words"], "ua": i["ua"], "ip": i["ip"], "age": int(now - i["t"])}
                    for i in self.items.values() if i["status"] == "pending"]

    def decide(self, rid, approve, token=None):
        with self._lock:
            self._prune()
            it = self.items.get(str(rid))
            if not it or it["status"] != "pending":
                return False
            it["status"] = "approved" if approve else "denied"
            # a token is only created now, for a request that is still pending
            it["token"] = (token() if callable(token) else token) if approve else None
            return True

    def status(self, rid):
        """{"status": ..., "token": ...}; the token is handed over exactly once."""
        with self._lock:
            self._prune()
            it = self.items.get(str(rid))
            if not it:
                return {"status": "expired"}
            out = {"status": it["status"]}
            if it["status"] == "approved" and it["token"]:
                out["token"], it["token"] = it["token"], None
            return out
