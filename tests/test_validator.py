import copy
import json
from pathlib import Path

import pytest

from genomde_dk_validator import DatenkranzValidator, classify

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def v():
    return DatenkranzValidator()


@pytest.fixture(scope="module")
def onc():
    return json.loads((FIX / "oncology_valid.json").read_text())


def test_classify(onc):
    assert classify(onc) == "oncology"
    assert classify({"donors": [], "submission": {}}) == "grz"
    assert classify({"case": {"diagnosisRd": {}}}) == "rare-disease"
    assert classify({"metadata": {}}) == "legacy-variant"


def test_valid_oncology(v, onc):
    r = v.validate(onc, "onc")
    assert r.branch == "oncology"
    assert r.schema_errors == [], r.schema_errors
    assert r.unknown_fields == [], r.unknown_fields
    assert r.ok() and r.ok(strict=True)


def test_valid_grz(v):
    r = v.validate_file(FIX / "grz_valid.json")
    assert r.branch == "grz"
    assert r.ok(), r.schema_errors


def test_unknown_field_detection(v, onc):
    d = copy.deepcopy(onc)
    d["bogusTopLevel"] = 1                       # unknown at root
    d["case"]["diagnosisOd"]["bogusNested"] = 2  # unknown deep in a $ref'd object
    r = v.validate(d, "onc+unknown")
    paths = {f.path for f in r.unknown_fields}
    assert "/bogusTopLevel" in paths
    assert "/case/diagnosisOd/bogusNested" in paths
    assert r.schema_errors == []          # unknowns are NOT schema errors (additionalProperties unset)
    assert r.ok() is True                 # warning by default
    assert r.ok(strict=True) is False     # error under --strict


def test_schema_error(v, onc):
    d = copy.deepcopy(onc)
    del d["metaData"]                     # required
    r = v.validate(d, "onc-broken")
    assert r.schema_errors and not r.ok()


def test_no_unknown_flag(onc):
    d = copy.deepcopy(onc)
    d["bogusTopLevel"] = 1
    r = DatenkranzValidator(check_unknown=False).validate(d)
    assert r.unknown_fields == []
