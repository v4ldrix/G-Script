"""Hub: events for the phone, prompts from the phone, extension heartbeat, preview images."""
import collections
import threading
import time

MAX_EVENTS = 300
MAX_IMAGES = 12


class Hub:
    def __init__(self):
        self.lock = threading.RLock()
        self.events = []
        self._next = 1
        self.outbox = []          # prompts typed on the phone, waiting for the chat tab
        self.decisions = {}       # approval id -> bool, decided on the phone
        self.pending = None       # approval currently waiting {"id", "calls"}
        self.stop_flag = False
        self.ext = {"active": False, "busy": False, "site": "", "state": "", "seen": 0.0}
        self.images = {}
        self._img_order = []
        self._img_next = 1
        self.logs = collections.deque(maxlen=200)   # shown in the desktop dashboard
        self.ui_seen = 0.0                          # last heartbeat from the dashboard window
        self.quit = False
        self.app_mode = False

    def log(self, line):
        self.logs.append(f"{time.strftime('%H:%M:%S')}  {line}")

    # ----- events -----
    def event(self, type_, text="", **extra):
        with self.lock:
            e = {"id": self._next, "ts": time.time(), "type": type_, "text": str(text)[:4000], **extra}
            self._next += 1
            self.events.append(e)
            del self.events[:-MAX_EVENTS]
            return e["id"]

    def since(self, last_id):
        with self.lock:
            return [e for e in self.events if e["id"] > last_id]

    def last_id(self):
        with self.lock:
            return self._next - 1

    # ----- phone -> PC -----
    def queue_prompt(self, text):
        with self.lock:
            pid = self.event("user", text)
            self.outbox.append({"id": pid, "text": str(text)[:4000]})
            return pid

    def decide(self, approval_id, approve):
        with self.lock:
            if self.pending and self.pending["id"] == approval_id:
                self.decisions[approval_id] = bool(approve)
                return True
            return False

    def request_stop(self):
        with self.lock:
            self.stop_flag = True
            self.outbox.clear()
            self.event("note", "Stop requested from phone")

    # ----- approvals -----
    def set_pending(self, pending):
        with self.lock:
            self.pending = {"id": pending["id"], "calls": pending.get("calls", [])}
            n = len(self.pending["calls"])
            self.event("approval", f"Approval needed for {n} step{'s' if n != 1 else ''}", approval=pending["id"])

    def clear_pending(self):
        with self.lock:
            self.pending = None
            self.decisions.clear()

    # ----- extension heartbeat -----
    def poll_ext(self, state):
        with self.lock:
            self.ext = {"active": bool(state.get("active")), "busy": bool(state.get("busy")),
                        "site": str(state.get("site", ""))[:60], "state": str(state.get("state", ""))[:40],
                        "seen": time.time()}
            prompts = []
            if self.ext["active"] and self.outbox:
                prompts, self.outbox = self.outbox, []
            autostart = (not self.ext["active"]) and bool(self.outbox)
            stop, self.stop_flag = self.stop_flag, False
            decisions = {}
            if self.pending and self.pending["id"] in self.decisions:
                decisions = {self.pending["id"]: self.decisions.pop(self.pending["id"])}
            return {"prompts": prompts, "autostart": autostart, "stop": stop, "decisions": decisions}

    def ext_view(self):
        with self.lock:
            e = dict(self.ext)
            e["connected"] = (time.time() - e.pop("seen")) < 6
            return e

    # ----- images -----
    def store_image(self, data, mime):
        with self.lock:
            iid = self._img_next
            self._img_next += 1
            self.images[iid] = (data, mime)
            self._img_order.append(iid)
            while len(self._img_order) > MAX_IMAGES:
                self.images.pop(self._img_order.pop(0), None)
            return iid

    def image(self, iid):
        with self.lock:
            return self.images.get(iid)
