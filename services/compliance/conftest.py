import os
from uuid import uuid4


def pytest_configure() -> None:
    os.environ.setdefault("COMPLIANCE_DATABASE_URL", os.getenv("COMPLIANCE_DATABASE_URL", ""))
    os.environ.setdefault("X_TENANT_ID_TEST", str(uuid4()))
