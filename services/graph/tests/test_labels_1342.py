"""Coverage sweep for services/graph/app/routers/labels.py (issue #1342).

Existing sibling tests (`test_labels_security.py`) cover the happy-path,
URL-encoding, tenant-dependency, and the generic exception branch in
``initialize_label_batch``. Coverage analysis against the module path
``services.graph.app.routers.labels`` still shows two uncovered lines:

* **Line 61** -- ``raise ValueError("GTIN must be exactly 14 digits")``
  inside ``ProductInfo.validate_gtin``. Pydantic short-circuits the
  validator when the ``min_length``/``max_length`` check fails, so the
  branch is only entered when a 14-character value sneaks through
  length validation but fails ``isdigit()`` (e.g. mixed alphanumerics).

* **Line 220** -- ``raise RuntimeError("Transaction returned no result")``
  inside ``initialize_label_batch`` when ``await result.single()``
  returns ``None``. The current error-handling test raises from
  ``session.run`` itself, which never reaches the ``if not record``
  guard. We exercise it by wiring ``result.single`` to return ``None``
  and asserting the guard is converted into the 500 HTTPException by
  the surrounding ``try/except``.

The tests follow the established pattern in ``test_labels_security.py``:
FastAPI ``TestClient`` for dependency-heavy paths and direct coroutine
calls with ``Neo4jClient`` patched out via ``unittest.mock``.

# Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Mirror the import bootstrap used by the sibling security tests so the
# module is loaded via ``services.graph.app.routers.labels`` (matches
# the coverage target configured for this sweep).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.routers.labels import (  # noqa: E402
    LabelBatchInitRequest,
    PackagingLevel,
    ProductInfo,
    TraceabilityInfo,
    UnitOfMeasure,
    initialize_label_batch,
)


class TestGTINValidatorRaises:
    """Covers line 61: ProductInfo.validate_gtin raising ValueError."""

    def test_gtin_with_non_digit_characters_raises(self):
        """A 14-char GTIN containing letters must fail ``isdigit()`` and
        trigger the explicit ``raise ValueError`` in ``validate_gtin``."""
        with pytest.raises(ValueError) as exc_info:
            # 14 chars so min_length/max_length pass, but not all digits
            # -> the validator's ``not v.isdigit()`` branch fires.
            ProductInfo(
                gtin="ABCDEFGHIJKLMN",
                description="Test Product",
                expected_units=1,
            )

        # Pydantic wraps the ValueError; the original message must survive
        # in the formatted validation error so the cause is auditable.
        assert "GTIN must be exactly 14 digits" in str(exc_info.value)

    def test_gtin_with_mixed_alphanumeric_raises(self):
        """A 14-char GTIN mixing digits and letters still hits line 61."""
        with pytest.raises(ValueError) as exc_info:
            ProductInfo(
                gtin="1234567890ABCD",
                description="Test Product",
                expected_units=1,
            )

        assert "GTIN must be exactly 14 digits" in str(exc_info.value)


class TestInitializeLabelBatchNoRecord:
    """Covers line 220: RuntimeError when ``result.single()`` is None."""

    @pytest.mark.asyncio
    async def test_none_record_converts_to_500(self):
        """If Neo4j returns no record, the inner ``RuntimeError`` must be
        translated to HTTP 500 by the surrounding ``try/except`` block."""
        mock_neo4j = MagicMock()
        mock_session = AsyncMock()
        mock_result = AsyncMock()

        # Trigger the ``if not record`` branch on line 219-220.
        mock_result.single = AsyncMock(return_value=None)
        mock_session.run = AsyncMock(return_value=mock_result)

        # Async context manager plumbing.
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_neo4j_class = MagicMock()
        mock_neo4j_class.return_value = mock_neo4j
        mock_neo4j.session = MagicMock(return_value=mock_session)
        mock_neo4j.close = AsyncMock()

        request = LabelBatchInitRequest(
            packer_gln="0614141000001",
            product=ProductInfo(
                gtin="00000012345678",
                description="Test Product",
                expected_units=1,
            ),
            traceability=TraceabilityInfo(
                lot_number="LOT-TEST-001",
                pack_date="2024-01-01",
            ),
            quantity=10,
            unit_of_measure=UnitOfMeasure.EA,
            packaging_level=PackagingLevel.ITEM,
        )

        test_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        with patch(
            "services.graph.app.routers.labels.Neo4jClient", mock_neo4j_class
        ):
            mock_neo4j_class.get_tenant_database_name = MagicMock(
                return_value="test-db"
            )
            with pytest.raises(HTTPException) as exc_info:
                await initialize_label_batch(
                    request=request,
                    tenant_id=test_tenant_id,
                    api_key="test-key",
                )

        # The RuntimeError on line 220 is caught and re-raised as 500.
        assert exc_info.value.status_code == 500
        assert "Database transaction failed" in exc_info.value.detail

        # Confirm the session was actually exercised (guarding against a
        # false positive where we skipped ``await result.single()``).
        assert mock_session.run.call_count == 1
        assert mock_result.single.call_count == 1
        # Cleanup ran even when the DB transaction aborted.
        mock_neo4j.close.assert_awaited_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
