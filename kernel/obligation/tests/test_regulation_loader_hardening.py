"""
Hardening tests for ``kernel.obligation.regulation_loader`` (#1351).

* Empty NEO4J_PASSWORD is refused unless the caller explicitly opts in.
* Env vars are read inside ``__init__``, not at class-definition time —
  so tests and per-worker config changes apply.
* ``load()`` runs the blocking Neo4j write off the event loop.
* When ``tenant_id`` is supplied, RegulatoryObligation nodes are written
  with the ``{obligation_id, tenant_id}`` shape the engine MATCHes.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kernel.obligation.regulation_loader import (
    RegulationLoader,
    _obligation_id_from_text,
)


# ---------------------------------------------------------------------------
# Empty password fails fast (#1351 part 3)
# ---------------------------------------------------------------------------


class TestEmptyPasswordRejected:
    def test_empty_password_raises_runtimeerror(self, monkeypatch):
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        with pytest.raises(RuntimeError, match="unauthenticated"):
            RegulationLoader(uri="bolt://localhost:7687", user="neo4j")

    def test_empty_password_with_opt_in_is_allowed(self, monkeypatch):
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        with patch("kernel.obligation.regulation_loader.GraphDatabase") as gdb:
            gdb.driver.return_value = MagicMock()
            loader = RegulationLoader(
                uri="bolt://localhost:7687",
                user="neo4j",
                password="",
                allow_empty_password=True,
            )
            assert loader.driver is not None

    def test_explicit_password_builds_driver(self):
        with patch("kernel.obligation.regulation_loader.GraphDatabase") as gdb:
            gdb.driver.return_value = MagicMock()
            loader = RegulationLoader(
                uri="bolt://localhost:7687",
                user="neo4j",
                password="secret",
            )
            assert loader.driver is not None
            gdb.driver.assert_called_once_with(
                "bolt://localhost:7687", auth=("neo4j", "secret")
            )


# ---------------------------------------------------------------------------
# Env reads happen at __init__ time (#1351 part 3)
# ---------------------------------------------------------------------------


class TestEnvReadAtCallTime:
    def test_env_change_between_constructions_applies(self, monkeypatch):
        """Env override in one test must not leak into the next call."""
        with patch("kernel.obligation.regulation_loader.GraphDatabase") as gdb:
            gdb.driver.return_value = MagicMock()

            monkeypatch.setenv("NEO4J_URI", "bolt://one:7687")
            monkeypatch.setenv("NEO4J_PASSWORD", "pw1")
            RegulationLoader()
            assert gdb.driver.call_args.args[0] == "bolt://one:7687"

            monkeypatch.setenv("NEO4J_URI", "bolt://two:7687")
            monkeypatch.setenv("NEO4J_PASSWORD", "pw2")
            RegulationLoader()
            assert gdb.driver.call_args.args[0] == "bolt://two:7687"


# ---------------------------------------------------------------------------
# _load_sync: tenant-scoped write shape (#1351 part 1)
# ---------------------------------------------------------------------------


class TestLoadTenantScopedWrite:
    def _build_loader_with_mock_driver(self):
        with patch("kernel.obligation.regulation_loader.GraphDatabase") as gdb:
            mock_session = MagicMock()
            mock_driver = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            mock_driver.session.return_value.__exit__.return_value = False
            gdb.driver.return_value = mock_driver

            loader = RegulationLoader(
                uri="bolt://x", user="neo4j", password="pw"
            )
        return loader, mock_session

    def test_tenant_id_None_skips_regulatory_obligation_write(self):
        loader, mock_session = self._build_loader_with_mock_driver()
        sections = [
            {
                "section_id": "1.1320",
                "title": "t",
                "text": "t",
                "citations": [],
                "obligations": ["shall record lot code"],
                "penalties": [],
                "jurisdiction": "FDA",
                "effective_date": None,
                "content_hash": "h",
            }
        ]
        loader._load_sync(sections, "21 CFR 1", "1.0", None)

        # With tenant_id=None we expect ONE session.run (the legacy shape).
        cypher_calls = [str(c.args[0]) for c in mock_session.run.call_args_list]
        assert not any(
            "RegulatoryObligation" in c for c in cypher_calls
        ), "RegulatoryObligation nodes should only be written when tenant_id is provided"

    def test_tenant_id_supplied_writes_regulatory_obligation(self):
        loader, mock_session = self._build_loader_with_mock_driver()
        sections = [
            {
                "section_id": "1.1320",
                "title": "t",
                "text": "t",
                "citations": [],
                "obligations": ["shall record lot code"],
                "penalties": [],
                "jurisdiction": "FDA",
                "effective_date": None,
                "content_hash": "h",
            }
        ]
        loader._load_sync(sections, "21 CFR 1", "1.0", "tenant-xyz")

        cypher_calls = [str(c.args[0]) for c in mock_session.run.call_args_list]
        assert any(
            "(ro:RegulatoryObligation" in c and "tenant_id" in c
            for c in cypher_calls
        ), "Expected RegulatoryObligation MERGE with tenant_id parameter"

    def test_tenant_scoped_rows_carry_stable_obligation_id(self):
        loader, mock_session = self._build_loader_with_mock_driver()
        sections = [
            {
                "section_id": "1.1320",
                "title": "t",
                "text": "t",
                "citations": [],
                "obligations": ["shall record lot code", "shall notify FDA"],
                "penalties": [],
                "jurisdiction": "FDA",
                "effective_date": None,
                "content_hash": "h",
            }
        ]
        loader._load_sync(sections, "21 CFR 1", "1.0", "tenant-xyz")

        # Find the call that writes RegulatoryObligation nodes.
        target = next(
            c for c in mock_session.run.call_args_list
            if "RegulatoryObligation" in str(c.args[0])
        )
        rows = target.kwargs["rows"]
        assert len(rows) == 2
        # Same text → same id. Stable across runs.
        assert rows[0]["obligation_id"] == _obligation_id_from_text("shall record lot code")
        assert rows[1]["obligation_id"] == _obligation_id_from_text("shall notify FDA")
        assert rows[0]["obligation_id"] != rows[1]["obligation_id"]


# ---------------------------------------------------------------------------
# load() uses to_thread (#1351 part 2)
# ---------------------------------------------------------------------------


class TestLoadUsesToThread:
    @pytest.mark.asyncio
    async def test_load_dispatches_to_thread(self):
        """``load()`` must run ``_load_sync`` via ``asyncio.to_thread`` so
        the blocking Neo4j write does not stall the event loop."""
        with patch("kernel.obligation.regulation_loader.GraphDatabase") as gdb:
            gdb.driver.return_value = MagicMock()
            loader = RegulationLoader(
                uri="bolt://x", user="neo4j", password="pw"
            )

        # Patch the parser so we don't try to import langchain / hit disk.
        fake_sections: List[Dict[str, Any]] = [
            {
                "section_id": "1",
                "title": "t",
                "text": "t",
                "citations": [],
                "obligations": [],
                "penalties": [],
                "jurisdiction": "FDA",
                "effective_date": None,
                "content_hash": "h",
            }
        ]
        with patch(
            "kernel.obligation.regulation_loader.RegulationParser"
        ) as mock_parser_cls, patch(
            "kernel.obligation.regulation_loader.asyncio.to_thread",
            new=AsyncMock(return_value=None),
        ) as mock_to_thread:
            mock_parser = MagicMock()
            mock_parser.parse = AsyncMock(return_value=fake_sections)
            mock_parser_cls.return_value = mock_parser

            result = await loader.load(
                "source.pdf", "pdf", "FSMA", tenant_id="t-1"
            )

            assert result == 1
            assert mock_to_thread.called
            args, _ = mock_to_thread.call_args
            # First positional arg is the callable — must be our sync worker.
            assert args[0] == loader._load_sync
            # tenant_id must be forwarded to _load_sync.
            assert args[-1] == "t-1"
