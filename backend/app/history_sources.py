"""Reuse only named, hash-checked static sources from this conversation."""
import hashlib
from pathlib import Path


def checked_history_sources(history, text: str, snapshot_id: str, data_dir: Path) -> list[dict]:
    base = (data_dir / 'sources' / snapshot_id).resolve()
    if not base.is_relative_to((data_dir / 'sources').resolve()):
        return []
    selected, seen = [], set()
    for message in history:
        if message.role != 'assistant':
            continue
        for source in message.citations or []:
            title, path = source.get('title', ''), source.get('path', '')
            if source.get('snapshot_id') != snapshot_id or not path.startswith('runtime/'):
                continue
            if source.get('evidence_type') in ('verified_ruling', 'user_statement') or not title or title not in text:
                continue
            file = (base / path).resolve()
            if not file.is_relative_to(base) or not file.is_file():
                continue
            raw = file.read_bytes()
            if source.get('sha256') != hashlib.sha256(raw).hexdigest():
                continue
            start, end = source.get('line_start'), source.get('line_end')
            if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= len(raw.decode('utf-8').splitlines()):
                continue
            key = (path, start, end, title)
            if key not in seen:
                seen.add(key)
                selected.append({'source': source, 'from_message_id': message.id})
            if len(selected) == 4:
                return selected
    return selected
