from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_enabled_outbound_http.py"
SPEC = importlib.util.spec_from_file_location("check_enabled_outbound_http", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)

scan_source = guard.scan_source
validate_paths = guard.validate_paths


def test_release_enabled_outbound_paths_use_pinned_http_layer() -> None:
    assert validate_paths() == []


def test_guard_detects_module_and_aliased_raw_clients() -> None:
    source = """
import httpx as hx
from requests import get as raw_get
from requests.sessions import Session as RawSession
import requests.sessions as req_sessions

def fetch(url):
    with hx.Client() as client:
        return client.get(url)

def fetch_again(url):
    return raw_get(url)

def fetch_session(url):
    return RawSession().get(url)

def fetch_submodule(url):
    return req_sessions.Session().get(url)
"""

    violations = scan_source(Path("fixture.py"), source)

    assert [(item.line, item.call) for item in violations] == [
        (8, "httpx.Client"),
        (12, "requests.get"),
        (15, "requests.Session"),
        (18, "requests.Session"),
    ]
