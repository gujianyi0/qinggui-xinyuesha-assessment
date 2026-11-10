"""Route using adapter metadata, never nicknames or identity claims in message text."""

from __future__ import annotations

import html
import re
from typing import Any

from .config import BridgeConfig

CQ_AT = re.compile(r"\[CQ:at,qq=(\d+)\]")
CQ_CODE = re.compile(r"\[CQ:[^\]]*\]")


def _integer(value: Any, *, positive: bool = True) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean ID is invalid")
    result = int(value)
    if positive and result <= 0:
        raise ValueError("ID must be positive")
    return result


def normalize_event(event: dict[str, Any], config: BridgeConfig) -> dict[str, Any] | None:
    if event.get("post_type") != "message" or event.get("message_type") not in {"private", "group"}:
        return None
    if event.get("anonymous") or event.get("sub_type") in {"anonymous", "notice"}:
        return None
    try:
        bot = _integer(event.get("self_id"))
        sender = _integer(event.get("user_id"))
        message_id = _integer(event.get("message_id"), positive=False)
        group = _integer(event.get("group_id")) if event["message_type"] == "group" else None
    except (TypeError, ValueError):
        return None
    if bot != config.self_id or sender == bot:
        return None
    if group is None and sender not in config.allowed_private_users:
        return None
    if group is not None and group not in config.allowed_groups:
        return None

    message = event.get("message")
    mentioned = False
    if isinstance(message, list):
        text_parts = []
        for segment in message:
            if not isinstance(segment, dict):
                return None
            kind, payload = segment.get("type"), segment.get("data", {})
            if not isinstance(payload, dict):
                return None
            if kind == "text":
                text_parts.append(str(payload.get("text", "")))
            elif kind == "at":
                mentioned = mentioned or str(payload.get("qq")) == str(bot)
            elif kind != "reply":
                return None  # v1 accepts text only; media does not silently lose meaning.
        text = "".join(text_parts).strip()
    else:
        raw = event.get("raw_message", message)
        if not isinstance(raw, str):
            return None
        mentioned = any(int(value) == bot for value in CQ_AT.findall(raw))
        without_at = CQ_AT.sub("", raw)
        if CQ_CODE.search(without_at):
            return None
        text = html.unescape(without_at).strip()
    prefixed = text.startswith(config.command_prefix)
    if group is not None and not mentioned and not prefixed:
        return None
    if prefixed:
        text = text[len(config.command_prefix):].lstrip(" ：:")
    if not text or len(text) > 8000:
        return None
    return {
        "self_id": bot,
        "user_id": sender,
        "message_type": event["message_type"],
        "group_id": group,
        "message_id": message_id,
        "raw_message": text,
    }


def delivery_target_allowed(delivery: dict[str, Any], config: BridgeConfig) -> bool:
    try:
        if _integer(delivery.get("self_id")) != config.self_id:
            return False
        sender = _integer(delivery.get("user_id"))
        if sender == config.self_id:
            return False
        if delivery.get("message_type") == "private":
            return sender in config.allowed_private_users
        if delivery.get("message_type") == "group":
            return _integer(delivery.get("group_id")) in config.allowed_groups
    except (TypeError, ValueError):
        return False
    return False
