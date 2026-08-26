from __future__ import annotations

from shared.agent_task_bridge import AGENT_ARTIFACT_TASK_TYPE
from shared.task_queue import TASK_HANDLERS, clear_task_handlers


def test_disabled_optional_router_handlers_are_not_registered(monkeypatch) -> None:
    import server.main as main

    class ProductionPolicy:
        @staticmethod
        def is_enabled(name: str) -> bool:
            assert name in {"sources", "scraping", "discovery"}
            return False

    clear_task_handlers()
    monkeypatch.setattr(main, "_ROUTER_POLICY", ProductionPolicy())
    try:
        registered = main._register_ingestion_task_handlers()

        assert registered == frozenset({"regulation_ingest", AGENT_ARTIFACT_TASK_TYPE})
        assert set(TASK_HANDLERS) == set(registered)
        assert {
            "federal_register_ingest",
            "ecfr_ingest",
            "fda_ingest",
            "state_scrape",
            "generic_scrape",
            "discovery_scrape",
        }.isdisjoint(TASK_HANDLERS)
    finally:
        clear_task_handlers()
