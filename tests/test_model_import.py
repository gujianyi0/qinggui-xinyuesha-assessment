import json
import sys

import pytest
from dotenv import dotenv_values

from scripts import import_qinggui_model as importer


def prepare(tmp_path, monkeypatch, contents):
    source = tmp_path / "authorized-source"
    source.mkdir()
    (source / ".env").write_text(contents, encoding="utf-8")
    target = tmp_path / "assessment"
    (target / "docs/evidence").mkdir(parents=True)
    (target / ".env.example").write_text("MODEL_MODE=mock\n", encoding="utf-8")
    monkeypatch.setattr(importer, "ROOT", target)
    monkeypatch.setattr(sys, "argv", ["import-model", "--source", str(source)])
    return source, target


def test_import_only_model_configuration_and_never_print_secret(tmp_path, monkeypatch, capsys):
    source, target = prepare(tmp_path, monkeypatch, "DEEPSEEK_API_KEY=fixture-secret-not-real\nONEBOT_SELF_ID=private-id\nQINGGUI_OWNER_NICKNAME=old-preference\n")
    override = source / "data/dashboard/model-config.json"
    override.parent.mkdir(parents=True)
    override.write_text(json.dumps({"model": "deepseek-v4-pro"}), encoding="utf-8")
    importer.main()
    values = dotenv_values(target / ".env")
    assert values["MODEL_ID"] == "deepseek-v4-pro"
    assert values["MODEL_INPUT_CNY_PER_MILLION"] == "9"
    assert values["MODEL_API_KEY"] == "fixture-secret-not-real"
    assert not any(key.startswith(("ONEBOT", "QINGGUI")) for key in values)
    assert "fixture-secret-not-real" not in capsys.readouterr().out
    evidence = (target / "docs/evidence/model-configuration-20261110.json").read_text(encoding="utf-8")
    assert "fixture-secret-not-real" not in evidence and "private-id" not in evidence


@pytest.mark.parametrize("contents", ["", "DEEPSEEK_API_KEY=fixture\nDEEPSEEK_BASE_URL=https://unknown.invalid\n", "DEEPSEEK_API_KEY=fixture\nDEEPSEEK_MODEL=unknown\n"])
def test_missing_credential_or_unknown_pricing_leaves_target_unchanged(tmp_path, monkeypatch, contents):
    _, target = prepare(tmp_path, monkeypatch, contents)
    with pytest.raises(ValueError):
        importer.main()
    assert not (target / ".env").exists()
