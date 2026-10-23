"""Empty and missing input paths must not synthesize bills, rules, or graph records."""

import io

import pytest
from app import local_factory, seed_neo4j
from extract import extract_ir
from pipeline import approve, deploy_and_record, main as pipeline_main, run as pipeline_run, verify_chain_cmd
from schemas import DeonticIR


def test_extraction_without_text_has_no_rule(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "unused")
    ir, reason = extract_ir(" \n ")
    assert ir is None
    assert reason.startswith("No data yet")


def test_extraction_without_model_has_no_fallback(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    ir, reason = extract_ir("supplied text")
    assert ir is None
    assert reason == "No data yet: OLLAMA_MODEL unset"


def test_pipeline_without_text_does_not_connect(monkeypatch, capsys):
    monkeypatch.setattr("pipeline.pg_connect", lambda: pytest.fail("unexpected database connection"))
    assert pipeline_run() == {"message": "No data yet"}
    assert pipeline_main(["run"]) == 0
    assert '"message": "No data yet"' in capsys.readouterr().out


def test_pipeline_missing_or_blank_file_does_not_connect(monkeypatch, tmp_path):
    monkeypatch.setattr("pipeline.pg_connect", lambda: pytest.fail("unexpected database connection"))
    assert pipeline_run(tmp_path / "missing.txt") == {"message": "No data yet"}
    blank = tmp_path / "blank.txt"
    blank.write_text(" \n ")
    assert pipeline_run(blank) == {"message": "No data yet"}


def test_approval_without_cases_does_not_connect_or_deploy(monkeypatch):
    monkeypatch.setattr("pipeline.pg_connect", lambda: pytest.fail("unexpected database connection"))
    monkeypatch.setattr("pipeline.deploy_to_opa", lambda *_: pytest.fail("unexpected deployment"))
    assert approve("") == {"message": "No data yet: evaluation cases required"}
    assert deploy_and_record(None, None, "", "", "") == {
        "message": "No data yet: evaluation cases required",
        "evaluations": [],
        "receipts": [],
    }


def test_chain_check_without_tenant_does_not_read_key(monkeypatch):
    monkeypatch.setattr("pipeline.load_or_create_signing_key", lambda: pytest.fail("unexpected key read"))
    assert verify_chain_cmd("") == {"message": "No data yet"}


def test_local_factory_without_selection_does_not_connect(monkeypatch, capsys):
    monkeypatch.setattr(local_factory, "pg_connect", lambda: pytest.fail("unexpected database connection"))
    monkeypatch.setattr(local_factory, "LegiScanClient", lambda *_: pytest.fail("unexpected API client"))
    assert local_factory.main([]) == 0
    assert capsys.readouterr().out.strip() == "No data yet"
    assert local_factory.format_matrix([]) == "No data yet"


def test_live_bill_without_text_does_not_call_model(monkeypatch):
    class EmptyBillClient:
        def fetch_latest_bill_text(self, _):
            return {"full_text": ""}

    monkeypatch.setattr(local_factory, "extract_deontic_ir_from_text", lambda *_: pytest.fail("unexpected model call"))
    with pytest.raises(local_factory.LiveBillError, match="No data yet"):
        local_factory.process_single_bill(None, EmptyBillClient())


def test_empty_graph_does_not_open_session():
    class NoSessionDriver:
        def session(self):
            pytest.fail("unexpected Neo4j session")

    out = io.StringIO()
    assert seed_neo4j.run(NoSessionDriver(), out=out) == []
    assert out.getvalue().strip() == "No data yet"
    assert seed_neo4j.run(NoSessionDriver(), {}, out=io.StringIO()) == []


def test_missing_graph_path_does_not_connect(tmp_path, capsys):
    assert seed_neo4j.main(["--graph", str(tmp_path / "missing.json")]) == 0
    assert capsys.readouterr().out.strip() == "No data yet"


def test_missing_ir_fields_are_rejected():
    with pytest.raises(ValueError):
        DeonticIR.model_validate({})
