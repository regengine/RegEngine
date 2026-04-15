"""Shared fixtures for golden-path integration tests.

These tests exercise production spine modules directly (no HTTP).
They do NOT require running services — the parent conftest's autouse
health check is overridden here.
"""

from typing import List
from unittest.mock import MagicMock

import pytest

from tests.integration.golden_path.helpers import GOLDEN_RULE_SEEDS
from shared.rules.types import RuleDefinition


@pytest.fixture(autouse=True)
async def check_services_health():
    """Override parent conftest — golden-path tests do not need running services."""
    pass


@pytest.fixture
def golden_rules() -> List[RuleDefinition]:
    """Provide the golden-path rule set for testing."""
    return GOLDEN_RULE_SEEDS


@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session that records operations."""
    session = MagicMock()
    session.execute.return_value = MagicMock(fetchall=MagicMock(return_value=[]))
    return session
