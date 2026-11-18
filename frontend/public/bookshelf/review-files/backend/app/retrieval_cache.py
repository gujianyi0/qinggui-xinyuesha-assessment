"""Validate cached retrieval receipts before exposing them to the model/UI."""

import re


def valid_cached_result(value, *, snapshot_id: str, top_k: int, mode: str) -> bool:
    if not isinstance(value, dict) or set(value) != {"mode", "snapshot_id", "items"}:
        return False
    if value["snapshot_id"] != snapshot_id or value["mode"] != mode:
        return False
    items = value["items"]
    if not isinstance(items, list) or len(items) > top_k:
        return False
    for item in items:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("id", "title", "text")):
            return False
        if not item["id"] or len(item["text"]) > 2200:
            return False
        source = item.get("source")
        if not isinstance(source, dict) or source.get("snapshot_id") != snapshot_id:
            return False
        if not all(isinstance(source.get(k), str) and source[k] for k in ("id", "path", "evidence_type", "sha256")):
            return False
        if not re.fullmatch(r"[a-f0-9]{64}", source["sha256"]):
            return False
        start, end = source.get("line_start"), source.get("line_end")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end:
            return False
    return True
