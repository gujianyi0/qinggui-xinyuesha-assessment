import json
from pathlib import Path

import pytest

from evaluations.run import validate_suite


def test_missing_source_field_is_rejected_before_paid_evaluation():
    with pytest.raises(ValueError, match='before paid requests'):
        validate_suite({'case_set':'bad','cases':[{'id':'AR01','category':'rules','messages':['question'],
                                                  'expected':{'judgment':'answer'},'source_checks':[]}]})


def test_fixed_suite_remains_valid_and_duplicate_ids_are_rejected():
    suite = json.loads((Path(__file__).resolve().parents[1] / 'evaluations/cases.json').read_text(encoding='utf-8'))
    validate_suite(suite)
    suite['cases'].append(suite['cases'][0])
    with pytest.raises(ValueError, match='Duplicate'):
        validate_suite(suite)
