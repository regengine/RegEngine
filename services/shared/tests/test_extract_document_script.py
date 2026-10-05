"""``scripts/extract_document.py``: extract a local document from the command line.

Offline: the extractor the script builds is swapped for one that carries a
fake SDK client, so nothing reaches the network. The contract under test is
the script's exit-code and output surface:

* without a key, or with the kill switch, exit 2 and nothing is uploaded;
* a missing, empty, unsupported or oversized document and an unreadable or
  non-object schema file exit 1 before anything is read into a request;
* a vendor failure exits 3 with the stable reason;
* success prints the data with its evidence line, or one JSON report with
  ``--json``; ``--tier`` / ``--version`` override the environment for the run;
* ``--prompt-key`` reads the key from stdin when there is no terminal and
  never prints it;
* run as a process without a key, it exits 2 with no traceback.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import structlog
from llama_cloud import AuthenticationError, _polling
from shared.document_extract import DocumentExtractor, DocumentExtractSettings

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "extract_document.py"
FAKE_KEY = "llx-extract-test-key-51e0"  # pragma: allowlist secret
SCHEMA = {"type": "object", "properties": {"lot_code": {"type": "string"}}}
EXTRACTED = {"lot_code": "LOT-9"}


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("extract_document", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["extract_document"] = module
    spec.loader.exec_module(module)
    return module


def _job(data: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        id="job-7",
        status="COMPLETED",
        extract_result=EXTRACTED if data is None else data,
        configuration=SimpleNamespace(tier="agentic", version="2026-10-01"),
        extract_metadata=SimpleNamespace(
            field_metadata=SimpleNamespace(
                document_metadata={"lot_code": {"confidence": 0.95, "citation": []}},
                page_metadata=None,
                row_metadata=None,
            ),
            parse_job_id="parse-7",
            parse_tier="agentic",
        ),
        metadata=SimpleNamespace(usage=SimpleNamespace(num_pages_extracted=1, num_pages_billed=1)),
        usage=SimpleNamespace(credits=15.0, extract_credits=15.0, parse_credits=0.0),
    )


class FakeFiles:
    def __init__(self, create_error: BaseException | None = None) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.create_error = create_error

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.created.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        return SimpleNamespace(id="file-7", name=kwargs["file"][0], project_id="proj")

    def delete(self, file_id: str, **kwargs: Any) -> None:
        self.deleted.append(file_id)


class FakeExtract:
    def __init__(self, run_error: BaseException | None = None) -> None:
        self.runs: list[dict[str, Any]] = []
        self.run_error = run_error

    def run(self, **kwargs: Any) -> SimpleNamespace:
        self.runs.append(kwargs)
        if self.run_error is not None:
            raise self.run_error
        return _job()


class FakeClient:
    def __init__(self, *, create_error: BaseException | None = None, run_error: BaseException | None = None) -> None:
        self.files = FakeFiles(create_error)
        self.extract = FakeExtract(run_error)
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_structlog():
    """main() configures structlog for the run; leave no configuration behind for other tests."""
    yield
    structlog.reset_defaults()


@pytest.fixture
def sdk(script, monkeypatch) -> FakeClient:
    """Hand the script an extractor that talks to a fake SDK client; return the client."""
    fake = FakeClient()

    def build(settings: DocumentExtractSettings, **kwargs: Any) -> DocumentExtractor:
        return DocumentExtractor(settings, client=fake)

    monkeypatch.setattr(script, "DocumentExtractor", build)
    return fake


@pytest.fixture
def env(monkeypatch):
    """A clean, keyed environment; the extract-related variables start unset."""
    for name in list(__import__("os").environ):
        if name.startswith("REGENGINE_DOC_EXTRACT_") or name in ("LLAMA_CLOUD_API_KEY", "LLAMA_CLOUD_BASE_URL"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", FAKE_KEY)
    return monkeypatch


@pytest.fixture
def document(tmp_path: Path) -> Path:
    path = tmp_path / "receiving.pdf"
    path.write_bytes(b"%PDF-1.4 receiving log")
    return path


@pytest.fixture
def schema_file(tmp_path: Path) -> Path:
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(SCHEMA), encoding="utf-8")
    return path


def test_extracts_and_prints_data_with_evidence(script, sdk, env, document, schema_file, capsys):
    code = script.main([str(document), "--schema", str(schema_file), "--tier", "agentic_plus", "--version", "latest"])
    out, err = capsys.readouterr()
    assert code == script.EXIT_OK, err
    assert out.startswith("Extracted: receiving.pdf")
    assert "job=job-7 tier=agentic version=2026-10-01 target=per_doc" in out
    assert json.dumps(EXTRACTED, indent=2) in out
    assert "document_extract.completed" not in out and "document_extract.completed" not in err
    assert FAKE_KEY not in out and FAKE_KEY not in err

    upload = sdk.files.created[0]
    assert upload["file"][0] == "receiving.pdf" and upload["file"][1] == b"%PDF-1.4 receiving log"
    (run,) = sdk.extract.runs
    config = run["configuration"]
    assert config["data_schema"] == SCHEMA
    assert config["tier"] == "agentic_plus"
    assert config["version"] == "latest"
    assert config["extraction_target"] == "per_doc"
    assert sdk.files.deleted == ["file-7"]
    assert sdk.closed is True


def test_json_report_carries_data_evidence_and_confidence(script, sdk, env, document, schema_file, capsys):
    code = script.main([str(document), "--schema", str(schema_file), "--json", "--target", "per_page"])
    out, _ = capsys.readouterr()
    assert code == script.EXIT_OK
    report = json.loads(out)
    assert report["data"] == EXTRACTED
    assert report["evidence"]["job_id"] == "job-7"
    assert report["evidence"]["extraction_target"] == "per_page"
    assert report["evidence"]["schema_version"] == "file:schema.json"
    assert report["confidence"]["fields"] == 1
    assert sdk.extract.runs[0]["configuration"]["extraction_target"] == "per_page"


def test_verbose_sends_wrapper_log_lines_to_stderr_only(script, sdk, env, document, schema_file, capsys):
    code = script.main([str(document), "--schema", str(schema_file), "--json", "--verbose"])
    out, err = capsys.readouterr()
    assert code == script.EXIT_OK
    assert json.loads(out)["data"] == EXTRACTED
    assert "document_extract.completed" in err
    assert "LOT-9" not in err and FAKE_KEY not in err


def test_default_schema_is_the_supplier_schema_and_rows_print(script, sdk, env, document, monkeypatch, capsys):
    supplier_result = {"facilities": [], "ftl_scopes": [], "tlcs": [], "events": []}
    monkeypatch.setattr(sdk.extract, "run", lambda **kwargs: _job(supplier_result))
    code = script.main([str(document), "--rows"])
    out, _ = capsys.readouterr()
    assert code == script.EXIT_OK
    assert "Bulk-upload parser rows (0):" in out


def test_without_key_nothing_is_sent(script, sdk, env, document, schema_file, capsys):
    env.delenv("LLAMA_CLOUD_API_KEY")
    code = script.main([str(document), "--schema", str(schema_file)])
    _, err = capsys.readouterr()
    assert code == script.EXIT_NOT_CONFIGURED
    assert "set LLAMA_CLOUD_API_KEY or pass --prompt-key" in err
    assert sdk.files.created == [] and sdk.extract.runs == []


def test_kill_switch_reports_switched_off(script, sdk, env, document, schema_file, capsys):
    env.setenv("REGENGINE_DOC_EXTRACT_ENABLED", "0")
    code = script.main([str(document), "--schema", str(schema_file)])
    _, err = capsys.readouterr()
    assert code == script.EXIT_NOT_CONFIGURED
    assert "switched off (REGENGINE_DOC_EXTRACT_ENABLED)" in err
    assert sdk.files.created == []


def test_prompt_key_reads_stdin_without_a_terminal_and_never_prints_it(
    script, env, document, schema_file, monkeypatch, capsys
):
    env.delenv("LLAMA_CLOUD_API_KEY")
    fake = FakeClient()
    seen: dict[str, str | None] = {}

    def build(settings: DocumentExtractSettings, **kwargs: Any) -> DocumentExtractor:
        seen["api_key"] = settings.api_key
        return DocumentExtractor(settings, client=fake)

    monkeypatch.setattr(script, "DocumentExtractor", build)
    monkeypatch.setattr(sys, "stdin", io.StringIO("typed-key-77\n"))  # pragma: allowlist secret
    code = script.main([str(document), "--schema", str(schema_file), "--prompt-key"])
    out, err = capsys.readouterr()
    assert code == script.EXIT_OK, err
    assert seen["api_key"] == "typed-key-77"  # pragma: allowlist secret
    assert "typed-key-77" not in out and "typed-key-77" not in err


def test_empty_prompt_key_is_a_usage_error(script, sdk, env, document, schema_file, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
    code = script.main([str(document), "--schema", str(schema_file), "--prompt-key"])
    _, err = capsys.readouterr()
    assert code == script.EXIT_USAGE
    assert "no key entered" in err
    assert sdk.files.created == []


def test_vendor_auth_failure_exits_unavailable(script, env, document, schema_file, monkeypatch, capsys):
    import httpx

    response = httpx.Response(401, request=httpx.Request("POST", "https://api.cloud.llamaindex.ai/x"), json={})
    fake = FakeClient(create_error=AuthenticationError("nope", response=response, body=None))
    monkeypatch.setattr(script, "DocumentExtractor", lambda settings, **kw: DocumentExtractor(settings, client=fake))
    code = script.main([str(document), "--schema", str(schema_file)])
    _, err = capsys.readouterr()
    assert code == script.EXIT_UNAVAILABLE
    assert "Extract unavailable: auth (status=401)" in err


def test_failed_job_exits_unavailable_and_deletes_the_upload(script, env, document, schema_file, monkeypatch, capsys):
    fake = FakeClient(run_error=_polling.PollingError("Job job-7 failed with status: FAILED"))
    monkeypatch.setattr(script, "DocumentExtractor", lambda settings, **kw: DocumentExtractor(settings, client=fake))
    code = script.main([str(document), "--schema", str(schema_file)])
    _, err = capsys.readouterr()
    assert code == script.EXIT_UNAVAILABLE
    assert "Extract unavailable: job_failed" in err
    assert fake.files.deleted == ["file-7"]


@pytest.mark.parametrize(
    ("make_path", "message"),
    [
        (lambda d: d / "missing.pdf", "is not a file"),
        (lambda d: _write(d / "notes.md", b"# notes"), "unsupported file type"),
        (lambda d: _write(d / "empty.pdf", b""), "is empty"),
    ],
)
def test_bad_document_exits_usage_before_sending(script, sdk, env, tmp_path, capsys, make_path, message):
    code = script.main([str(make_path(tmp_path))])
    _, err = capsys.readouterr()
    assert code == script.EXIT_USAGE
    assert message in err
    assert sdk.files.created == []


def test_oversized_document_exits_usage(script, sdk, env, document, capsys):
    code = script.main([str(document), "--max-bytes", "4"])
    _, err = capsys.readouterr()
    assert code == script.EXIT_USAGE
    assert "--max-bytes is 4" in err
    assert sdk.files.created == []


@pytest.mark.parametrize(
    ("schema_text", "message"),
    [
        ("{not json", "cannot read schema"),
        ("[]", "must be a JSON object schema"),
        ('{"type": "array"}', "must be a JSON object schema"),
    ],
)
def test_bad_schema_file_exits_usage_before_sending(script, sdk, env, document, tmp_path, capsys, schema_text, message):
    bad = tmp_path / "bad.json"
    bad.write_text(schema_text, encoding="utf-8")
    code = script.main([str(document), "--schema", str(bad)])
    _, err = capsys.readouterr()
    assert code == script.EXIT_USAGE
    assert message in err
    assert sdk.files.created == []


def test_bad_tier_is_rejected_by_the_parser(script, sdk, env, document):
    with pytest.raises(SystemExit) as info:
        script.main([str(document), "--tier", "premium"])
    assert info.value.code == 2
    assert sdk.files.created == []


def test_runs_as_a_process_without_a_key(document, schema_file):
    """The script's own bootstrap: importable from the repo, exit 2 and nothing sent without a key."""
    env = {"PATH": "/usr/bin:/bin", "LLAMA_CLOUD_API_KEY": ""}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(document), "--schema", str(schema_file)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 2, proc.stderr
    assert "not configured" in proc.stderr
    assert "Traceback" not in proc.stderr


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path
