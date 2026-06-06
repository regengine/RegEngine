import os
from uuid import uuid4

import pytest


def _configure_compliance_test_env() -> None:
    os.environ.setdefault("COMPLIANCE_DATABASE_URL", os.getenv("COMPLIANCE_DATABASE_URL", ""))
    os.environ["REGENGINE_ENV"] = "test"
    os.environ["AUTH_TEST_BYPASS_TOKEN"] = "test-bypass-token-compliance"
    os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-compliance")


def pytest_configure() -> None:
    _configure_compliance_test_env()
    os.environ.setdefault("X_TENANT_ID_TEST", str(uuid4()))


@pytest.fixture(autouse=True)
def _pin_compliance_test_env() -> None:
    """Keep auth bypass enabled for compliance tests during full-suite runs."""
    _configure_compliance_test_env()
