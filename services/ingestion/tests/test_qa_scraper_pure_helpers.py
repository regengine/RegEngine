"""QA: characterization tests for untested pure helpers in scope.

Pins the behavior of small deterministic functions with no existing
coverage: ``regulation_parser`` extraction helpers, the NYDFS
``_retry_delay`` / visible-text helpers, and the queue/task key builders.
No network, no sleeps, no fixtures beyond monkeypatch-free unit calls.
"""

from __future__ import annotations


class TestExtractCitations:
    def test_cfr_citation_extracted(self):
        from app.regulation_parser import extract_citations

        assert "21 CFR 123.4" in extract_citations("see 21 CFR 123.4 for details")

    def test_section_symbol_extracted(self):
        from app.regulation_parser import extract_citations

        found = extract_citations("as required by section 12.3 of the rule")
        assert found, "expected at least one citation from a section reference"

    def test_empty_text_returns_empty(self):
        from app.regulation_parser import extract_citations

        assert extract_citations("") == []

    def test_no_citations_returns_empty(self):
        from app.regulation_parser import extract_citations

        assert extract_citations("wash hands before handling food") == []

    def test_results_are_deduplicated(self):
        from app.regulation_parser import extract_citations

        found = extract_citations("21 CFR 123.4 and again 21 CFR 123.4")
        assert found.count("21 CFR 123.4") == 1


class TestExtractRequirements:
    def test_shall_sentence_extracted(self):
        from app.regulation_parser import extract_requirements

        reqs = extract_requirements("You shall record the lot code. Wash hands.")
        assert any("shall" in r.lower() for r in reqs)

    def test_must_and_required_matched(self):
        from app.regulation_parser import extract_requirements

        reqs = extract_requirements("Facilities must register. Testing is required. Nice day.")
        assert len(reqs) == 2

    def test_empty_text_returns_empty(self):
        from app.regulation_parser import extract_requirements

        assert extract_requirements("") == []

    def test_no_modal_verbs_returns_empty(self):
        from app.regulation_parser import extract_requirements

        assert extract_requirements("The sky is blue. Grass is green.") == []


class TestDetectJurisdiction:
    def test_fda_keyword(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._detect_jurisdiction("per FDA guidance") == "FDA"

    def test_fsma_keyword_maps_to_fda(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._detect_jurisdiction("under FSMA section 204") == "FDA"

    def test_cfr_without_fda_maps_to_federal(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._detect_jurisdiction("per the CFR title 21") == "US-FEDERAL"

    def test_fda_wins_over_plain_cfr(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._detect_jurisdiction("FDA enforces 21 CFR 1.1") == "FDA"

    def test_unknown_text(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._detect_jurisdiction("wash hands") == "UNKNOWN"


class TestExtractDate:
    def test_effective_date_us_format(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._extract_date("effective 01/15/2024 for all") == "01/15/2024"

    def test_dated_on_format(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._extract_date("dated on 03/04/2025, revision 2") == "03/04/2025"

    def test_iso_format_returned_verbatim(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._extract_date("published 2024-01-15 final") == "2024-01-15"

    def test_no_date_returns_none(self):
        from app.regulation_parser import RegulationParser

        assert RegulationParser()._extract_date("no dates here") is None


class TestNydfsRetryDelay:
    def test_none_returns_fallback(self):
        from app.scrapers.state_adaptors.nydfs import _retry_delay

        assert _retry_delay(None, 2.0) == 2.0

    def test_numeric_string_returned(self):
        from app.scrapers.state_adaptors.nydfs import _retry_delay

        assert _retry_delay("5", 2.0) == 5.0

    def test_garbage_returns_fallback(self):
        from app.scrapers.state_adaptors.nydfs import _retry_delay

        assert _retry_delay("not-a-number", 2.0) == 2.0

    def test_infinite_retry_after_falls_back(self):
        # A hostile or buggy Retry-After: inf would hang the worker in
        # time.sleep(inf); it must degrade to the fallback instead.
        from app.scrapers.state_adaptors.nydfs import _retry_delay

        assert _retry_delay("inf", 2.0) == 2.0

    def test_nan_retry_after_falls_back(self):
        from app.scrapers.state_adaptors.nydfs import _retry_delay

        assert _retry_delay("nan", 2.0) == 2.0


class TestNydfsVisibleText:
    def test_script_and_nav_stripped(self):
        from app.scrapers.state_adaptors.nydfs import _extract_visible_text

        html = (
            b"<html><body><nav>menu</nav>"
            b"<main>Important regulatory text</main>"
            b"<script>console.log('x')</script>"
            b"<footer>foot</footer></body></html>"
        )
        text = _extract_visible_text(html)
        assert "Important regulatory text" in text
        assert "console.log" not in text
        assert "menu" not in text

    def test_empty_content_returns_empty(self):
        from app.scrapers.state_adaptors.nydfs import _extract_visible_text

        assert _extract_visible_text(b"") == ""

    def test_style_stripped(self):
        from app.scrapers.state_adaptors.nydfs import _extract_visible_text

        text = _extract_visible_text(b"<html><style>.a{color:red}</style><p>rule text</p></html>")
        assert "rule text" in text
        assert "color" not in text


class TestKeyBuilders:
    def test_manual_queue_key_namespaces_tenant(self):
        from app.routes_discovery import _manual_queue_key

        assert _manual_queue_key("t-1") == "manual_upload_queue:t-1"
        assert _manual_queue_key("t-1") != _manual_queue_key("t-2")

    def test_discovery_task_key_stable_and_scoped(self):
        from app.routes_discovery import _discovery_task_key

        first = _discovery_task_key("t-1", "body", "https://x.example/1")
        assert first == _discovery_task_key("t-1", "body", "https://x.example/1")
        assert first.startswith("discovery_scrape:t-1:")
        assert first != _discovery_task_key("t-2", "body", "https://x.example/1")
        assert first != _discovery_task_key("t-1", "other", "https://x.example/1")

    def test_source_task_key_shape(self):
        from app.routes_sources import _source_task_key

        assert _source_task_key("fda_ingest", "t-9", "job-1") == "fda_ingest:t-9:job-1"

    def test_url_hash_deterministic(self):
        from app.routes_scraping import _url_hash

        assert _url_hash("https://x.example/1") == _url_hash("https://x.example/1")
        assert _url_hash("https://x.example/1") != _url_hash("https://x.example/2")
        assert len(_url_hash("https://x.example/1")) == 64
