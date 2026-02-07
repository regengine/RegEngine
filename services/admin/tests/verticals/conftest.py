"""Test configuration for healthcare vertical tests."""
import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    mock_session = MagicMock(spec=Session)
    
    # Configure common methods
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.flush = MagicMock()
    mock_session.rollback = MagicMock()
    
    return mock_session
