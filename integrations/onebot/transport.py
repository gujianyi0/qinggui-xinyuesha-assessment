"""Separate /event and /api connections with correlated OneBot echo replies."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any


class SendRejected(Exception):
    """The OneBot API explicitly rejected a request."""


class SendUnknown(Exception):
    """The transport cannot prove whether the remote service accepted a send."""


class OneBotAPI:
    def __init__(self, websocket: Any, timeout: float = 15.0):
        self.websocket = websocket
        self.timeout = timeout
        self._lock = asyncio.Lock()

    async def send_text(self, target: dict[str, Any], text: str) -> str:
        params: dict[str, Any] = {"message": text, "auto_escape": True}
        if target["message_type"] == "private":
            action = "send_private_msg"
            params["user_id"] = int(target["user_id"])
        else:
            action = "send_group_msg"
            params["group_id"] = int(target["group_id"])
        echo = uuid.uuid4().hex
        async with self._lock:
            try:
                async with asyncio.timeout(self.timeout):
                    await self.websocket.send(json.dumps({"action": action, "params": params, "echo": echo}))
                    while True:
                        response = json.loads(await self.websocket.recv())
                        if not isinstance(response, dict) or response.get("echo") != echo:
                            continue
                        if response.get("status") == "failed" or response.get("retcode", 0) not in {0, 1}:
                            raise SendRejected(f"onebot_retcode_{response.get('retcode', 'unknown')}")
                        data = response.get("data")
                        if response.get("status") != "ok" or not isinstance(data, dict) or data.get("message_id") is None:
                            raise SendUnknown("onebot_ack_missing_message_id")
                        return str(data["message_id"])
            except SendRejected:
                raise
            except SendUnknown:
                raise
            except Exception as exc:
                raise SendUnknown(type(exc).__name__) from exc
