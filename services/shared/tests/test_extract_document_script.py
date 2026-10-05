"""``scripts/extract_document.py``: extract a document from the command line.

Offline (``httpx.MockTransport``): the document and schema go up as the API
takes them, the result prints with its evidence line, ``--json``/``--out``
carry the full result, and the key is never printed. Without a key nothing
is sent; bad arguments exit 1 before anything is read.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import structlog

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "extract_document.py"
FAKE_KEY = "llx-extract-test-key-51e0"  # pragma: allowlist secret
ENV = {"LLAMA_CLOUD_API_KEY": FAKE_KEY}
SCHEMA = {"type": "object", "properties": {"lot_code": {"type": "string"}}}
JOB = {
    "id": "job_7",
    "created_at": "2026-10-05T10:00:00Z",
    "updated_at": "2026-10-05T10:00:00Z",
    "file_input": "file_7",
    "project_id": "proj",
    "status": "COMPLETED",
    "configuration": {"data_schema": SCHEMA, "tier": "agentic", "version": "2.5.0-2026-10-01"},
    "extract_result": {"lot_code": "LOT-9"},
    "extract_metadata": {"field_metadata": {"document_metadata": {"lot_code": {"confidence": 0.95}}}},
    "metadata": {"usage": {"num_pages_billed": 1, "num_pages_extracted": 1}},
}


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("extract_document", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["extract_document"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def cli_logging(script):
    """What ``__main__`` does before anything logs: warnings and above to stderr, stdout stays the result."""
    script._configure_cli_logging()
    yield
    structlog.reset_defaults()


class _Server:
    def __init__(self, *, job=None, upload_status: int = 200):
        self.requests: list[httpx.Request] = []
        self.job = JOB if job is None else job
        self.upload_status = upload_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(self.upload_status, json={"id": "file_7", "name": "x.pdf", "project_id": "proj"})
        if request.url.path == "/api/v2/extract" and request.method == "POST":
            return httpx.Response(200, json={**self.job, "status": "PENDING", "extract_result": None})
        if request.url.path == "/api/v2/extract/job_7":
            return httpx.Response(200, json=self.job)
        return httpx.Response(404, json={"detail": request.url.path})


def _client(server: _Server) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(server))


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


def test_extracts_and_prints_data_with_evidence_line(script, document, schema_file, capsys):
    server = _Server()
    code = script.main(
        ["--file", str(document), "--schema", str(schema_file), "--tier", "agentic_plus", "--pages", "1"],
        env=ENV,
        http_client=_client(server),
    )
    out, err = capsys.readouterr()
    assert code == script.EXIT_OK, err
    assert json.loads(out.split("\n-- ")[0]) == {"lot_code": "LOT-9"}
    assert "-- extracted by llama_cloud extract_v2 tier=agentic_plus version=2.5.0-2026-10-01 job=job_7" in out
    assert FAKE_KEY not in out and FAKE_KEY not in err

    upload, create, _poll = server.requests
    assert b'filename="receiving.pdf"' in upload.content and b"receiving log" in upload.content
    config = json.loads(create.content)["configuration"]
    assert config["data_schema"] == SCHEMA
    assert config["tier"] == "agentic_plus"
    assert config["version"] == "2.5"
    assert config["target_pages"] == "1"


def test_json_and_out_carry_the_full_result(script, document, tmp_path, capsys):
    out_path = tmp_path / "result.json"
    code = script.main(
        ["--file", str(document), "--schema-inline", json.dumps(SCHEMA), "--json", "--out", str(out_path)],
        env=ENV,
        http_client=_client(_Server()),
    )
    out, _ = capsys.readouterr()
    assert code == script.EXIT_OK
    printed = json.loads(out)
    assert printed["data"] == {"lot_code": "LOT-9"}
    assert printed["field_metadata"] == {"target": "per_doc", "fields": {"lot_code": {"confidence": 0.95}}}
    assert printed["evidence"]["job_id"] == "job_7"
    assert printed["evidence"]["requested_version"] == "2.5"
    assert json.loads(out_path.read_text(encoding="utf-8")) == printed


def test_without_key_nothing_is_sent(script, document, schema_file, capsys):
    server = _Server()
    code = script.main(["--file", str(document), "--schema", str(schema_file)], env={}, http_client=_client(server))
    _, err = capsys.readouterr()
    assert code == script.EXIT_NOT_CONFIGURED
    assert "LLAMA_CLOUD_API_KEY is not set" in err and "Nothing was sent" in err
    assert server.requests == []


def test_kill_switch_reports_not_configured(script, document, schema_file, capsys):
    server = _Server()
    code = script.main(
        ["--file", str(document), "--schema", str(schema_file)],
        env={**ENV, "REGENGINE_LLAMA_EXTRACT_ENABLED": "0"},
        http_client=_client(server),
    )
    _, err = capsys.readouterr()
    assert code == script.EXIT_NOT_CONFIGURED
    assert "switches Extract off" in err
    assert server.requests == []


def test_prompt_key_is_used_and_never_printed(script, document, schema_file, capsys):
    server = _Server()
    code = script.main(
        ["--file", str(document), "--schema", str(schema_file), "--prompt-key"],
        env={},
        http_client=_client(server),
        read_key=lambda prompt: "typed-key-77\n",  # pragma: allowlist secret
    )
    out, err = capsys.readouterr()
    assert code == script.EXIT_OK, err
    assert server.requests[0].headers["authorization"] == "Bearer typed-key-77"
    assert "typed-key-77" not in out and "typed-key-77" not in err


def test_vendor_failure_exits_unavailable(script, document, schema_file, capsys):
    code = script.main(
        ["--file", str(document), "--schema", str(schema_file)],
        env=ENV,
        http_client=_client(_Server(upload_status=401)),
    )
    _, err = capsys.readouterr()
    assert code == script.EXIT_UNAVAILABLE
    assert "unavailable: auth (status 401)" in err


def test_failed_job_exits_unavailable(script, document, schema_file, capsys):
    failed = {**JOB, "status": "FAILED", "error_message": "unreadable scan", "extract_result": None}
    code = script.main(
        ["--file", str(document), "--schema", str(schema_file)],
        env=ENV,
        http_client=_client(_Server(job=failed)),
    )
    _, err = capsys.readouterr()
    assert code == script.EXIT_UNAVAILABLE
    assert "unavailable: job_failed" in err


@pytest.mark.parametrize(
    ("argv_tail", "message"),
    [
        (["--schema-inline", "{not json"], "is not valid JSON"),
        (["--schema-inline", "[]"], "non-empty JSON object"),
        (["--schema", "/nonexistent/schema.json"], "cannot read --schema"),
        (["--schema-inline", "{}", "--tier", "premium"], "invalid choice"),
    ],
)
def test_bad_arguments_exit_usage_before_sending(script, document, capsys, argv_tail, message):
    server = _Server()
    code = script.main(["--file", str(document), *argv_tail], env=ENV, http_client=_client(server))
    _, err = capsys.readouterr()
    assert code == script.EXIT_USAGE
    assert message in err
    assert server.requests == []


def test_missing_document_exits_usage(script, schema_file, capsys):
    server = _Server()
    code = script.main(
        ["--file", "/nonexistent/doc.pdf", "--schema", str(schema_file)], env=ENV, http_client=_client(server)
    )
    _, err = capsys.readouterr()
    assert code == script.EXIT_USAGE
    assert "is not a file" in err
    assert server.requests == []


def test_runs_as_a_process_without_a_key(document, schema_file):
    """The script's own bootstrap: importable from the repo, exit 2 and nothing sent without a key."""
    env = {"PATH": "/usr/bin:/bin", "LLAMA_CLOUD_API_KEY": ""}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(document), "--schema", str(schema_file)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 2, proc.stderr
    assert "not configured" in proc.stderr
    assert "Traceback" not in proc.stderr
