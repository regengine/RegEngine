"""Regression test for issue #1234.

find_entity_by_alias must emit ORDER BY confidence_score DESC, created_at ASC
so the first match is deterministic when multiple aliases resolve to different
canonical entities.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService

TENANT = "tenant-cccccccc-cccc-cccc-cccc-cccccccccccc"


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    session.execute.return_value.fetchone.return_value = (1,)
    return session


@pytest.fixture
def svc(mock_session):
    return IdentityResolutionService(mock_session)


class TestFindByAliasOrderBy_Issue1234:
    def test_order_by_confidence_then_created_at_in_sql(self, svc, mock_session):
        """The SQL emitted by find_entity_by_alias must contain ORDER BY so
        that the first active match is deterministic across Postgres page
        layouts."""
        svc.find_entity_by_alias(TENANT, "gln", "0614141000012")

        assert mock_session.execute.called
        sql, _params = mock_session.execute.call_args_list[0].args
        sql_text = str(sql).replace("\n", " ").lower()

        assert "order by" in sql_text, (
            "find_entity_by_alias SQL must contain ORDER BY to prevent "
            "non-deterministic results (#1234)"
        )
        assert "confidence_score" in sql_text, (
            "ORDER BY must include confidence_score DESC as primary sort key"
        )
        assert "created_at" in sql_text, (
            "ORDER BY must include created_at ASC as tiebreak"
        )

    def test_order_by_confidence_desc_created_at_asc(self, svc, mock_session):
        """Verify the ordering direction: highest confidence first, earliest
        created_at as tiebreak (so oldest registration wins on equal score)."""
        svc.find_entity_by_alias(TENANT, "gln", "0614141000012")

        sql, _params = mock_session.execute.call_args_list[0].args
        sql_text = str(sql).replace("\n", " ").lower()

        # Extract the ORDER BY clause for direction checks
        order_by_pos = sql_text.find("order by")
        assert order_by_pos != -1, "ORDER BY not found in SQL"
        order_clause = sql_text[order_by_pos:]

        # confidence_score DESC should appear before created_at in the ORDER BY
        conf_pos = order_clause.find("confidence_score")
        created_pos = order_clause.find("created_at")
        assert 0 <= conf_pos < created_pos, (
            "confidence_score must appear before created_at in ORDER BY"
        )

        # Check DESC on confidence_score and ASC on created_at
        assert "confidence_score desc" in order_clause, (
            "confidence_score must be sorted DESC"
        )
        assert "created_at asc" in order_clause, (
            "created_at must be sorted ASC (oldest registration wins on tie)"
        )
