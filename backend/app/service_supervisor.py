"""A Worker failure degrades background jobs without tearing down the website."""
from collections import deque


class WorkerSupervisor:
    def __init__(self, process, spawn, stop, record, *, memory_limit=3 * 1024**3,
                 max_restarts=5, window=600, name="worker"):
        self.process, self.spawn, self.stop, self.record = process, spawn, stop, record
        self.name = name
        self.memory_limit, self.max_restarts, self.window = memory_limit, max_restarts, window
        self.restarts, self.due = deque(), None
        self.status = {"state": "running", "pid": process.pid, "restart_count": 0, "last_exit": None}

    async def tick(self, now, *, private_bytes=0):
        if self.status["state"] == "circuit_open":
            return
        code = self.process.poll()
        if code is None and private_bytes > self.memory_limit:
            self.record({"event": f"{self.name}_memory_limit", "pid": self.process.pid,
                         "private_bytes": private_bytes, "limit": self.memory_limit})
            await self.stop(self.process)
            code = self.process.poll()
        if code is None:
            return
        if self.due is None:
            self.status["last_exit"] = {"pid": self.process.pid, "code": code}
            while self.restarts and self.restarts[0] < now - self.window:
                self.restarts.popleft()
            self.record({"event": f"{self.name}_exited", **self.status["last_exit"]})
            if len(self.restarts) >= self.max_restarts:
                self.status["state"] = "circuit_open"
                self.record({"event": f"{self.name}_circuit_open", "restart_count": self.status["restart_count"]})
                return
            self.due = now + min(30, 2 ** len(self.restarts))
            self.status["state"] = "backoff"
        if now >= self.due:
            try:
                replacement = self.spawn()
            except Exception as error:
                # A failed launch counts toward the same bounded retry budget.
                self.record({"event": f"{self.name}_spawn_failed", "error_type": type(error).__name__})
                self.restarts.append(now)
                self.due = None
                return
            self.restarts.append(now)
            self.process, self.due = replacement, None
            self.status.update(state="running", pid=replacement.pid, restart_count=self.status["restart_count"] + 1)
            self.record({"event": f"{self.name}_restarted", "pid": replacement.pid, "restart_count": self.status["restart_count"]})
