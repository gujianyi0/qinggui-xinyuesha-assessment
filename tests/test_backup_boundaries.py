import pytest

from scripts.backup_docker_primary import label_path, restore_check


def test_backup_labels_cannot_escape_private_backup_directory():
    for label in ('../outside', 'a/b', r'a\b', '', '..', 'A'):
        with pytest.raises(ValueError):
            label_path(label)


def test_restore_never_accepts_primary_or_arbitrary_database():
    for database in ('assessment', 'postgres', 'assessment_eval_v19', 'assessment_restore_a;DROP DATABASE assessment'):
        with pytest.raises(ValueError):
            restore_check('valid-label', database)


def test_busy_primary_is_rejected_before_any_writer_is_stopped(monkeypatch, tmp_path):
    from scripts import backup_docker_primary as module
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'relay_running', lambda: False)
    monkeypatch.setattr(module, 'fingerprint', lambda: {'active':{'runs':1},'budget':{'reserved':0}})
    commands=[]
    monkeypatch.setattr(module, 'checked', lambda *args: commands.append(args))
    with pytest.raises(ValueError, match='仍有运行'):
        module.backup('busy-refused')
    assert not commands
