"""Freeze and statically extract the approved FreeKill Lua packages.

No Lua, game executable, configuration or player database is executed/read by this
extractor. JSON outputs are portable: all citations use snapshot-relative paths.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("standard", "standard_cards", "maneuvering")
VERSION = "static-lua-v1.1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lua_string(text: str, pos: int) -> tuple[str, int] | None:
    """Decode only a literal string; never evaluate Lua expressions."""
    long = re.match(r"\[(=*)\[", text[pos:])
    if long:
        start = pos + long.end()
        end = text.find("]" + long[1] + "]", start)
        if end < 0:
            raise ValueError(f"Unterminated Lua long string at {pos}")
        value = text[start:end]
        if value.startswith("\r\n"):
            value = value[2:]
        elif value.startswith("\n"):
            value = value[1:]
        return value, end + len(long[1]) + 2
    if pos >= len(text) or text[pos] not in "\"'":
        return None
    quote, chars = text[pos], []
    pos += 1
    escapes = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    while pos < len(text):
        ch = text[pos]
        pos += 1
        if ch == quote:
            return "".join(chars), pos
        if ch != "\\":
            chars.append(ch)
            continue
        if pos >= len(text):
            break
        ch = text[pos]
        pos += 1
        if ch in escapes:
            chars.append(escapes[ch])
        elif ch == "z":
            while pos < len(text) and text[pos].isspace():
                pos += 1
        elif ch.isdigit():
            digits = ch
            while pos < len(text) and text[pos].isdigit() and len(digits) < 3:
                digits += text[pos]
                pos += 1
            chars.append(chr(int(digits)))
        elif ch == "x":
            chars.append(chr(int(text[pos:pos+2], 16)))
            pos += 2
        elif ch == "u" and text[pos:pos+1] == "{":
            end = text.index("}", pos)
            chars.append(chr(int(text[pos+1:end], 16)))
            pos = end + 1
        else:
            chars.append(ch)
    raise ValueError("Unterminated Lua quoted string")


def translations(text: str) -> dict[str, tuple[str, int, int]]:
    values: dict[str, tuple[str, int, int]] = {}
    for match in re.finditer(r"\[\s*([\"'])", text):
        key = lua_string(text, match.end() - 1)
        if key is None:
            continue
        after = re.match(r"\s*\]\s*=\s*", text[key[1]:])
        if not after:
            continue
        start = key[1] + after.end()
        value = lua_string(text, start)
        if value is None:
            continue
        # Only literal concatenation is supported; a function call is never run.
        combined, end = value
        while (concat := re.match(r"\s*\.\.\s*", text[end:])):
            following = lua_string(text, end + concat.end())
            if following is None:
                break
            combined += following[0]
            end = following[1]
        values[key[0]] = (combined, text.count("\n", 0, match.start()) + 1,
                          text.count("\n", 0, end) + 1)
    return values


def plain(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def table_blocks(text: str, call: str):
    """Find balanced literal table arguments, skipping quoted strings/comments."""
    for match in re.finditer(re.escape(call) + r"\s*\{", text):
        start = match.end()
        pos, depth = start, 1
        while pos < len(text) and depth:
            if text.startswith("--", pos):
                literal = lua_string(text, pos + 2)
                pos = literal[1] if literal else (text.find("\n", pos) if "\n" in text[pos:] else len(text))
                continue
            literal = lua_string(text, pos)
            if literal:
                pos = literal[1]
                continue
            depth += (text[pos] == "{") - (text[pos] == "}")
            pos += 1
        if depth:
            raise ValueError(f"Unbalanced {call} table")
        yield text[start:pos-1], match.start(), pos


def extract(source: Path, destination: Path = ROOT / "data") -> dict:
    if not (source / "runtime/packages/standard/pkg/init.lua").is_file():
        raise ValueError("Expected the approved FreeKill source checkout, not a distribution directory")
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    snapshot_id = f"freekill-local-{commit[:12]}"
    copied = destination / "sources" / snapshot_id
    files: list[dict] = []
    # Files are explicitly limited to textual source and license material.
    selected = [source / "LICENSE"]
    for package in PACKAGES:
        base = source / "runtime/packages" / package
        selected += sorted(base.rglob("*.lua"))
        selected += [p for p in base.glob("*LICENSE*") if p.is_file()]
    for src in selected:
        if src.is_symlink():
            raise ValueError(f"Symlink source is not allowed: {src.name}")
        rel = src.relative_to(source).as_posix()
        data = src.read_bytes()
        target = copied / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append({"path": rel, "sha256": digest(data), "bytes": len(data)})
    by_path = {item["path"]: item for item in files}
    catalog, documents = [], []

    def cite(path: str, first: int, last: int, title: str, excerpt: str, kind: str) -> dict:
        return {"id": digest(f"{snapshot_id}:{path}:{first}:{last}".encode())[:20],
                "title": title, "path": path, "line_start": first, "line_end": last,
                "snapshot_id": snapshot_id, "evidence_type": kind,
                "excerpt": excerpt, "sha256": by_path[path]["sha256"]}

    def add_doc(identifier: str, title: str, body: str, package: str, citation: dict):
        if not body.strip():
            return
        # Split by headings/paragraphs, preserving exact source spans in citations.
        chunks = re.split(r"\n(?=##? )", body) if len(body) > 2200 else [body]
        for index, chunk in enumerate(chunks):
            if chunk.strip():
                documents.append({"id": f"{identifier}:{index}", "title": title,
                                  "text": plain(chunk), "package": package, "source": citation})

    translations_all: dict[str, tuple[str, int, int, str]] = {}
    for package in PACKAGES:
        paths = [f"runtime/packages/{package}/pkg/init.lua", f"runtime/packages/{package}/i18n/zh_CN.lua"]
        trans = {}
        for path in paths:
            p = copied / path
            if p.is_file():
                for key, (value, first, last) in translations(p.read_text(encoding="utf-8-sig")).items():
                    trans[key] = (value, first, last, path)
        translations_all.update(trans)
        init_path = paths[0]
        text = (copied / init_path).read_text(encoding="utf-8-sig")
        # Simple General:new literal calls are the authoritative general registry.
        pattern = r'General:new\(extension,\s*"([^"]+)",\s*"([^"]+)",\s*(\d+)([^)]*)\):addSkills\s*\{([^}]+)\}'
        for match in re.finditer(pattern, text):
            identifier, kingdom, hp, rest, skill_text = match.groups()
            name, first, last, name_path = trans.get(identifier, (identifier, 1, 1, init_path))
            skills = re.findall(r'"([^"]+)"', skill_text)
            if identifier == "anjiang":
                continue
            hp_max = re.match(r"\s*,\s*(\d+)", rest)
            attributes = {"internal_id": identifier, "kingdom": kingdom, "hp": int(hp),
                          "max_hp": int(hp_max[1]) if hp_max else int(hp),
                          "gender": "female" if "General.Female" in rest else "male", "skills": skills}
            desc = "\n".join(f"{trans.get(s, (s,))[0]}：{plain(trans.get(':'+s, ('资料缺失',))[0])}" for s in skills)
            start = text.count("\n", 0, match.start()) + 1
            citation = cite(init_path, start, text.count("\n", 0, match.end())+1, name, match[0], "implementation")
            catalog.append({"id": f"{package}:general:{identifier}", "kind": "general", "name": name,
                            "package": package, "description": desc, "attributes": attributes, "source": citation})
        for block, start, end in table_blocks(text, "fk.CreateCard"):
            name_match = re.search(r'\bname\s*=\s*"([^"]+)"', block)
            if not name_match:
                raise ValueError("Card definition without a literal name")
            identifier = name_match[1]
            name = trans.get(identifier, (identifier,))[0]
            attributes = {"internal_id": identifier}
            for field in ("type", "sub_type", "damage_type", "skill", "equip_skill", "attack_range", "is_damage_card", "is_passive"):
                found = re.search(r"\b" + field + r"\s*=\s*([^,\n]+)", block)
                if found:
                    raw = found[1].strip()
                    literal = lua_string(raw, 0)
                    value = literal[0] if literal else int(raw) if raw.isdigit() else raw == "true" if raw in {"true", "false"} else raw
                    attributes[field] = value
            specs = re.findall(r'addCardSpec\("' + re.escape(identifier) + r'",\s*Card\.(\w+),\s*(\d+)\)', text)
            attributes["deck_specs"] = [{"suit": suit, "number": int(number)} for suit, number in specs]
            desc = plain(trans.get(":"+identifier, ("当前快照缺少中文说明",))[0])
            citation = cite(init_path, text.count("\n", 0, start)+1, text.count("\n", 0, end)+1,
                            name, text[start:end], "implementation")
            catalog.append({"id": f"{package}:card:{identifier}", "kind": "card", "name": name,
                            "package": package, "description": desc, "attributes": attributes, "source": citation})
        for key, (value, first, last, path) in trans.items():
            if not key.startswith(":"):
                continue
            internal = key[1:]
            title = trans.get(internal, (internal,))[0]
            citation = cite(path, first, last, title, value, "rule_text" if internal == "aaa_role_mode" else "skill_description")
            add_doc(f"{package}:text:{internal}", title, value, package, citation)
            # Description keys without card/general entries are player-facing skills.
            if internal != "aaa_role_mode" and not any(e["attributes"].get("internal_id") == internal for e in catalog):
                skill_files = list((copied / f"runtime/packages/{package}/pkg/skills").glob(internal + ".lua"))
                catalog.append({"id": f"{package}:skill:{internal}", "kind": "skill", "name": title,
                                "package": package, "description": plain(value),
                                "attributes": {"internal_id": internal, "implementation_available": bool(skill_files)}, "source": citation})
    # Keep implementation evidence for every skill in the chosen three packages.
    for item in files:
        path = item["path"]
        if "/pkg/skills/" not in path:
            continue
        text = (copied / path).read_text(encoding="utf-8-sig")
        package = path.split("/")[2]
        title = translations_all.get(Path(path).stem, (Path(path).stem,))[0]
        citation = cite(path, 1, len(text.splitlines()), title + "实现", text[:1800], "implementation")
        add_doc(f"implementation:{package}:{Path(path).stem}", title + "实现", text, package, citation)
    # This real conflict is not silently resolved into an invented game rule.
    mode_text = translations_all.get(":aaa_role_mode")
    if mode_text:
        value, first, last, path = mode_text
        mode_init = "runtime/packages/standard/pkg/init.lua"
        mode_source = (copied / mode_init).read_text(encoding="utf-8-sig")
        config = re.search(r"minPlayer\s*=\s*2\s*,\s*maxPlayer\s*=\s*8", mode_source)
        if "10人游戏" in value and config:
            first_config = mode_source.count("\n", 0, config.start())+1
            documents.append({"id": "known-conflict:role-player-count", "title": "身份模式人数：说明文字与模式配置冲突", "package": "standard",
                              "text": "本快照身份模式的说明文字提及10人游戏，但同一快照的实现配置 minPlayer=2、maxPlayer=8。只能确认文字与配置不一致，按本地配置人数上限为8；没有历史证据判断文字是否来自旧版，也不能判断冲突成因或线上服务器人数上限。",
                              "source": cite(mode_init, first_config, first_config+2, "身份模式配置", config[0], "implementation"),
                              "related_source": cite(path, first, last, "身份模式说明", "10人游戏时每人发2张", "rule_text")})
    manifest = {"snapshot_id": snapshot_id, "source_commit": commit,
                "client_version": (source / "runtime/fk_ver").read_text(encoding="utf-8").strip(),
                "label": "新月杀本地修改版 · 标准/标准牌/军争", "packages": list(PACKAGES),
                "extractor_version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
                "source_repository": "https://github.com/gujianyi0/xinyuesha-ios", "files": files,
                "counts": dict(Counter(e["kind"] for e in catalog)), "documents": len(documents),
                "limitations": ["只解析白名单静态字面量，不执行Lua", "不是当前线上服务器规则声明", "卡牌定义数量不是牌堆张数", "不包含freekill-core内部镜像"]}
    manifest_hash = digest(json.dumps({"commit": commit, "files": files, "extractor": VERSION}, sort_keys=True).encode())
    manifest["manifest_hash"] = manifest_hash
    write_json(destination / "manifest.json", manifest)
    write_json(destination / "catalog.json", catalog)
    write_json(destination / "documents.json", documents)
    write_json(destination / "snapshots.json", [{"id": snapshot_id, "label": manifest["label"], "active": True,
                                                "commit": commit, "manifest_hash": manifest_hash}])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Approved FreeKill maintenance checkout")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    result = extract(args.source.resolve(), args.output.resolve())
    print(json.dumps({"snapshot_id": result["snapshot_id"], "counts": result["counts"], "documents": result["documents"], "manifest_hash": result["manifest_hash"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
