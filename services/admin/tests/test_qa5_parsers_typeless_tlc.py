"""QA5: typeless bulk-upload rows carrying a lot code are lots, not events.

``_classify_row`` had two identical ``if row.get("tlc_code")`` branches:
the first (events) shadowed the second (TLCs) into dead code, so a CSV
without a ``record_type`` column could never create lots: every lot
row became an event with an empty ``cte_type`` and failed validation.
Typeless rows now classify as TLCs unless they carry event signals
(``cte_type``/timestamp/payload), which still classify as events.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.bulk_upload.parsers import parse_incoming_file  # noqa: E402


def _csv_upload(content: str):
    import io

    from starlette.datastructures import UploadFile

    return UploadFile(
        filename="supplier.csv",
        file=io.BytesIO(content.encode("utf-8")),
        headers={"content-type": "text/csv"},
    )


class TestTypelessTlcRows:
    def test_bare_tlc_row_becomes_tlc_not_event(self):
        """Pre-fix this row landed in ``events`` with ``cte_type == ""``
        and failed validation; lots could never be created from
        typeless files."""
        csv_content = "tlc_code,facility_name\nTLC-100,Salinas Packhouse\n"
        parsed = asyncio.run(parse_incoming_file(_csv_upload(csv_content)))

        assert len(parsed["tlcs"]) == 1
        assert parsed["tlcs"][0]["tlc_code"] == "TLC-100"
        assert parsed["tlcs"][0]["facility_name"] == "Salinas Packhouse"
        assert parsed["events"] == []

    def test_tlc_row_with_event_time_stays_event(self):
        """A typeless row that also carries a timestamp is an event
        missing its type, not a lot definition."""
        csv_content = "tlc_code,facility_name,event_time\nTLC-100,Salinas Packhouse,2026-03-03T12:00:00Z\n"
        parsed = asyncio.run(parse_incoming_file(_csv_upload(csv_content)))

        assert parsed["tlcs"] == []
        assert len(parsed["events"]) == 1
        assert parsed["events"][0]["tlc_code"] == "TLC-100"

    def test_tlc_row_with_cte_type_stays_event(self):
        csv_content = "tlc_code,facility_name,cte_type\nTLC-100,Salinas Packhouse,shipping\n"
        parsed = asyncio.run(parse_incoming_file(_csv_upload(csv_content)))

        assert parsed["tlcs"] == []
        assert len(parsed["events"]) == 1
        assert parsed["events"][0]["cte_type"] == "shipping"
