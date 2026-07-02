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


def test_meta_keys_not_flagged(v, onc):
    d = copy.deepcopy(onc)
    d["$schema"] = "https://example.org/grz-schema.json"     # editor hint at root
    d["$comment"] = "x"
    d["case"]["$id"] = "y"                                    # nested meta-key
    paths = {f.path for f in v.validate(d).unknown_fields}
    assert not any(p.split("/")[-1].startswith("$") for p in paths)


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


# --- semantic rules (BfArM QS) ---

def test_grz_rules_sanity_on_kdk(v, onc):
    r = v.validate(onc, "onc", rules="grz")
    assert any(f.rule_id == "grz-sanity" and f.level == "error" for f in r.rule_findings)


def test_kdk12_forbidden_noscope(v, onc):
    d = copy.deepcopy(onc)
    d["metaData"]["researchConsents"][0]["noScopeJustification"] = \
        "consent is not implemented at LE due to organizational issues"
    d["metaData"]["researchConsents"][0].pop("scope", None)
    ids = {f.rule_id for f in v.validate(d, rules="kdk").rule_errors}
    assert "kdk-12-noscope-justification" in ids


def test_kdk10_rare_librarytype(v, onc):
    d = copy.deepcopy(onc)
    d["metaData"]["submission"]["diseaseType"] = "rare"
    d["case"]["diagnosisOd"]["libraryType"] = "panel"   # panel excluded for rare
    ids = {f.rule_id for f in v.validate(d, rules="kdk").rule_errors}
    assert "kdk-10-rare-librarytype" in ids


def test_kdk3_index_consent_and_config_skip(v, onc):
    d = copy.deepcopy(onc)
    d["metaData"]["mvConsent"]["scope"] = [{"type": "deny", "domain": "mvSequencing", "date": "2026-03-24"}]
    findings = v.validate(d, rules="kdk").rule_findings
    assert any(f.rule_id == "kdk-3-index-consent-sequencing" and f.level == "error" for f in findings)
    # external-resource rules skip (info) with no config
    assert any(f.rule_id == "kdk-11-node-id" and f.level == "info" for f in findings)


def test_kdk11_config_enforced(v, onc):
    r = v.validate(onc, rules="kdk", rules_config={"clinical_data_node_id": "WRONG-NODE"})
    assert any(f.rule_id == "kdk-11-node-id" and f.level == "error" for f in r.rule_errors)


# --- robustness / review fixes ---

@pytest.mark.parametrize("bad", [None, 42, "x", [1, 2], {"case": "notadict"}, {"case": []}])
def test_hostile_input_no_crash(v, bad):
    r = v.validate(bad, "hostile")        # must not raise
    assert r.branch in ("grz", "oncology", "rare-disease", "legacy-variant", "unknown")


def test_fhirpath_engine_equivalent_to_primitive(v, onc):
    prim = {f.rule_id for f in v.validate(onc, rules="kdk", rules_engine="primitive").rule_errors}
    fhir = {f.rule_id for f in v.validate(onc, rules="kdk", rules_engine="fhirpath").rule_errors}
    assert prim == fhir


def test_fhirpath_config_skip_and_enforce(v, onc):
    skips = {f.rule_id for f in v.validate(onc, rules="kdk", rules_engine="fhirpath").rule_findings
             if f.level == "info"}
    assert "kdk-11-node-id" in skips          # skipped without config
    errs = {f.rule_id for f in v.validate(onc, rules="kdk", rules_engine="fhirpath",
                                          rules_config={"clinical_data_node_id": "WRONG"}).rule_errors}
    assert "kdk-11-node-id" in errs           # enforced with config


def test_malformed_json_reports_line(v, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{\n  "a": 1,\n  "b": 2\n  "c": 3\n}\n')   # missing comma on line 4
    r = v.validate_file(bad)
    assert not r.ok() and r.schema_errors[0].line == 4


def test_no_schema_branch_has_finding(v):
    r = v.validate({"metadata": {}})                          # legacy variant -> no root schema
    assert r.branch == "legacy-variant" and not r.ok()
    assert any(f.path == "(root)" for f in r.schema_errors)   # actionable, not a silent fail


def test_tnm_code_only_equivalent(v, onc):
    import copy
    d = copy.deepcopy(onc)
    d["case"]["diagnosisOd"]["tnmClassifications"] = [{"code": "cT2"}, {"code": "cN0"}]  # no M, category in code
    prim = {f.rule_id for f in v.validate(d, rules="kdk", rules_engine="primitive").rule_errors}
    fhir = {f.rule_id for f in v.validate(d, rules="kdk", rules_engine="fhirpath").rule_errors}
    assert "kdk-5-tnm-one-each" in prim and prim == fhir      # both read category from `code`, not just display


def test_date_tuple_rejects_junk():
    from genomde_dk_validator.rules import _date_tuple
    assert _date_tuple("2026-04-21") == (2026, 4, 21)
    assert _date_tuple("1975-08") == (1975, 8, 1)
    assert _date_tuple("2026-99-99x") is None
    assert _date_tuple("2026-13") is None
    assert _date_tuple("notadate") is None
