import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_snapshot", ROOT / "scripts/source_snapshot.py")
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


def read(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_snapshot_has_only_approved_packages_and_exact_source_hashes():
    manifest = read("manifest.json")
    assert manifest["packages"] == ["standard", "standard_cards", "maneuvering"]
    source = ROOT / "data/sources" / manifest["snapshot_id"]
    for record in manifest["files"]:
        assert "freekill-core" not in record["path"]
        assert ".." not in Path(record["path"]).parts
        path = source / record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        assert path.suffix == ".lua" or "LICENSE" in path.name


def test_known_general_and_card_registry_is_complete():
    entities = read("catalog.json")
    assert len([e for e in entities if e["kind"] == "general"]) == 25
    assert len([e for e in entities if e["kind"] == "card"]) == 43
    assert len({e["id"] for e in entities}) == len(entities)
    assert not any(e["attributes"]["internal_id"] == "anjiang" for e in entities)
    by_name = {e["name"]: e for e in entities}
    assert by_name["曹操"]["attributes"]["hp"] == 4
    assert by_name["甄姬"]["attributes"]["gender"] == "female"
    assert by_name["青龙偃月刀"]["attributes"]["attack_range"] == 3
    assert by_name["白银狮子"]["package"] == "maneuvering"
    assert "防止多余" in by_name["白银狮子"]["description"]


def test_all_citations_resolve_within_frozen_snapshot():
    manifest = read("manifest.json")
    root = ROOT / "data/sources" / manifest["snapshot_id"]
    for item in read("catalog.json") + read("documents.json"):
        source = item["source"]
        text = (root / source["path"]).read_text(encoding="utf-8-sig")
        assert source["snapshot_id"] == manifest["snapshot_id"]
        assert 1 <= source["line_start"] <= source["line_end"] <= len(text.splitlines()) + 1
        assert source["sha256"] == hashlib.sha256((root / source["path"]).read_bytes()).hexdigest()


def test_real_conflict_is_retained_instead_of_treated_as_a_single_rule():
    conflicts = [d for d in read("documents.json") if d["id"] == "known-conflict:role-player-count"]
    assert len(conflicts) == 1
    assert "10人" in conflicts[0]["text"]
    assert "maxPlayer=8" in conflicts[0]["text"]
    assert conflicts[0]["related_source"]["path"].endswith("zh_CN.lua")


def test_lua_literal_parser_preserves_chinese_and_decodes_escapes():
    assert extractor.lua_string('"中文\\n规则\\\""', 0)[0] == '中文\n规则"'
    assert extractor.lua_string('[==[\n多行\n文本]==]', 0)[0] == '多行\n文本'
    assert extractor.lua_string("os.execute('bad')", 0) is None
    values = extractor.translations('{["a"] = "甲" .. "乙", ["b"] = [=[丙]=]}')
    assert values["a"][0] == "甲乙"
    assert values["b"][0] == "丙"


def test_static_card_tables_skip_nested_strings_and_comments():
    text = 'fk.CreateCard{ name="safe", nested={a=1}, text="}", -- }\n active=true }'
    blocks = list(extractor.table_blocks(text, "fk.CreateCard"))
    assert len(blocks) == 1
    assert "active=true" in blocks[0][0]
