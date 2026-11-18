from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.app.history_sources import checked_history_sources


def fixture(app, source):
    return checked_history_sources([SimpleNamespace(id='previous', role='assistant', citations=[source])],
                                   '奸雄在受到伤害后发动', app.state.catalog.active_id, app.state.settings.data_dir)


@pytest.mark.parametrize('change', ['snapshot', 'hash', 'path', 'evidence', 'range', 'title'])
def test_history_reuse_rejects_wrong_snapshot_tamper_nonstatic_and_irrelevant_sources(app, change):
    source = deepcopy(next(entity['source'] for entity in app.state.catalog.entities if entity['id']=='standard:skill:jianxiong'))
    if change == 'snapshot':
        source['snapshot_id'] = 'other'
    if change == 'hash':
        source['sha256'] = '0'*64
    if change == 'path':
        source['path'] = 'runtime/../../outside.lua'
    if change == 'evidence':
        source['evidence_type'] = 'verified_ruling'
    if change == 'range':
        source['line_end'] = 999999
    if change == 'title':
        source['title'] = '护驾'
    assert fixture(app, source) == []


def test_history_reuse_deduplicates_only_assistant_static_sources(app):
    source = next(entity['source'] for entity in app.state.catalog.entities if entity['id']=='standard:skill:jianxiong')
    history = [SimpleNamespace(id='user',role='user',citations=[source]),
               SimpleNamespace(id='previous',role='assistant',citations=[source,source])]
    result = checked_history_sources(history,'奸雄技能',app.state.catalog.active_id,app.state.settings.data_dir)
    assert result == [{'source':source,'from_message_id':'previous'}]
