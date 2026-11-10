"""Configuration contains no inherited QQ accounts or conversation allowlists."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def parse_ids(value: str) -> frozenset[int]:
    values = frozenset(int(item.strip()) for item in value.split(",") if item.strip())
    if any(value <= 0 for value in values):
        raise ValueError("QQ allowlist IDs must be positive integers")
    return values


def websocket_endpoint(base: str, endpoint: str) -> str:
    parsed = urlsplit(base)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise ValueError("ONEBOT_WS_URL must be a ws:// or wss:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Put the OneBot access token in its separate environment variable")
    if parsed.path.rstrip("/") not in {"", "/api", "/event"}:
        raise ValueError("ONEBOT_WS_URL must point to the OneBot root, /api, or /event")
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{endpoint}", "", ""))


@dataclass(frozen=True)
class BridgeConfig:
    ws_url: str = "ws://127.0.0.1:3001"
    access_token: str = field(default="", repr=False)
    api_url: str = "http://127.0.0.1:8000"
    bridge_token: str = field(default="", repr=False)
    self_id: int = 0
    allowed_private_users: frozenset[int] = frozenset()
    allowed_groups: frozenset[int] = frozenset()
    original_listener_paused: bool = False
    state_path: Path = Path(".local/bridge/deliveries.sqlite3")
    send_timeout: float = 15.0
    backend_timeout: float = 180.0
    command_prefix: str = "/新月杀"

    @classmethod
    def from_env(cls) -> BridgeConfig:
        sessions = os.getenv("QQ_ALLOWED_SESSIONS", "").strip()
        private_ids, group_ids = set(), set()
        if sessions:
            for session in sessions.split(","):
                kind, separator, value = session.strip().partition(":")
                if not separator or kind not in {"private", "group"}:
                    raise ValueError("QQ_ALLOWED_SESSIONS uses private:ID,group:ID")
                parsed = parse_ids(value)
                (private_ids if kind == "private" else group_ids).update(parsed)
        return cls(
            ws_url=os.getenv("ONEBOT_WS_URL", "ws://127.0.0.1:3001"),
            access_token=os.getenv("ONEBOT_ACCESS_TOKEN", ""),
            api_url=os.getenv("BRIDGE_API_URL", "http://127.0.0.1:8000").rstrip("/"),
            bridge_token=os.getenv("BRIDGE_TOKEN", ""),
            self_id=int(os.getenv("QQ_BOT_ID", os.getenv("QQ_SELF_ID", "0"))),
            allowed_private_users=frozenset(private_ids) if sessions else parse_ids(os.getenv("QQ_ALLOWED_PRIVATE_USERS", "")),
            allowed_groups=frozenset(group_ids) if sessions else parse_ids(os.getenv("QQ_ALLOWED_GROUPS", "")),
            original_listener_paused=os.getenv("QQ_ORIGINAL_LISTENER_PAUSED", "").lower() == "true",
            state_path=Path(os.getenv("BRIDGE_STATE_PATH", ".local/bridge/deliveries.sqlite3")),
            send_timeout=float(os.getenv("ONEBOT_SEND_TIMEOUT", "15")),
            backend_timeout=float(os.getenv("BRIDGE_BACKEND_TIMEOUT", "180")),
        )

    def validate_live(self) -> None:
        websocket_endpoint(self.ws_url, "event")
        if self.self_id <= 0 or not self.bridge_token or not self.access_token:
            raise ValueError("Live mode requires QQ_BOT_ID, BRIDGE_TOKEN, and ONEBOT_ACCESS_TOKEN")
        if not self.allowed_private_users and not self.allowed_groups:
            raise ValueError("Live mode requires an explicitly configured conversation allowlist")
        if not self.original_listener_paused:
            raise ValueError("Pause the original reply listener and set QQ_ORIGINAL_LISTENER_PAUSED=true")
        if self.send_timeout <= 0 or self.backend_timeout <= 0:
            raise ValueError("Timeouts must be positive")
        parsed = urlsplit(self.api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("BRIDGE_API_URL must be an HTTP(S) base URL without credentials")
