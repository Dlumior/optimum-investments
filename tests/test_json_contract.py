import copy

import pytest

from optimum import paths
from optimum.io.json_contract import validate_input

pytestmark = pytest.mark.skipif(not paths.INPUT_JSON.exists(), reason="ejecuta `make json`")


@pytest.fixture(scope="module")
def doc():
    import json

    return json.loads(paths.INPUT_JSON.read_text(encoding="utf-8"))


def test_generated_input_is_valid(doc):
    assert validate_input(doc) == []
    assert len(doc["marketHistory"]) == 60
    assert len(doc["factorMapping"]["factorIds"]) == 24


def test_rejects_duplicate_history(doc):
    bad = copy.deepcopy(doc)
    bad["marketHistory"].append(bad["marketHistory"][-1])
    assert any("duplicadas" in e for e in validate_input(bad))


def test_rejects_unknown_segment(doc):
    bad = copy.deepcopy(doc)
    bad["marketHistory"][0]["forwardSwap"]["PEN"]["S9"] = 0.05
    assert any("segmentos inexistentes" in e for e in validate_input(bad))


def test_rejects_undefined_float_reference(doc):
    bad = copy.deepcopy(doc)
    bad["instruments"][2]["reference_factor"] = "PEN_FWD_S7"
    assert any("no definido" in e for e in validate_input(bad))
