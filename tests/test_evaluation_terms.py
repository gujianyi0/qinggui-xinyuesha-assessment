import pytest

from evaluations.run import mechanical_checks


@pytest.mark.parametrize("text,expected", [("酒只能对自己使用", True), ("酒只能对本人使用", True), ("酒可以自救", True), ("酒可以给其他角色", False)])
def test_term_aliases_are_transparent_and_not_semantic_scores(text, expected):
    result = mechanical_checks({"expected": {"terms_all": ["自己"]}}, [], {"text": text})
    assert result["expected_terms_present"] is expected
    assert result["literal_terms_present"] == ("自己" in text)
    assert result["human_review_pending"] is True
