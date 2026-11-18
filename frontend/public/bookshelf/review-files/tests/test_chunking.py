import pytest

from backend.app.chunking import chunk_documents


def test_chunking_covers_tail_keeps_overlap_and_source_offsets():
    text = "开头" + "中" * 1000 + "尾部关键裁定"
    document = {"id": "long-rule", "text": text, "source": {"id": "origin", "path": "rules.lua", "line_start": 1, "line_end": 20}}
    chunks = chunk_documents([document])
    assert len(chunks) > 1 and all(len(chunk["text"]) <= 320 for chunk in chunks)
    assert chunks[-1]["text"].endswith("尾部关键裁定")
    rebuilt = chunks[0]["text"]
    for previous, current in zip(chunks, chunks[1:]):
        assert previous["text"][-64:] == current["text"][:64]
        rebuilt += current["text"][64:]
    assert rebuilt == text
    assert len({chunk["id"] for chunk in chunks}) == len(chunks)
    for chunk in chunks:
        source = chunk["source"]
        assert source["path"] == "rules.lua" and source["line_end"] == 20
        assert text[source["char_start"]:source["char_end"]] == chunk["text"]


def test_short_document_keeps_original_identity():
    document = {"id": "short", "text": "简短规则", "source": {"id": "origin"}}
    assert chunk_documents([document]) == [document]


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_chunking_limits_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunk_documents([], size, overlap)
