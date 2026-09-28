"""Real-S3 round trip for raw ingestion storage, backed by testcontainers.

The S3 API is served by LocalStack (``SERVICES=s3``) running in a throwaway
container. MinIO images are no longer publicly pullable: the docker.io
repository was removed, and quay.io/minio/minio now rejects anonymous pulls
with ``401 unauthorized``, which failed both ingestion CI jobs at fixture
setup. LocalStack is the S3 emulator backend CI already runs as the
``localstack`` service container of the ``Test`` job.
"""

import json

import boto3
import pytest
from botocore.config import Config
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

# localstack/localstack:3.8.1, pinned by its multi-arch index digest so the
# image cannot change under the test. The ``localstack/localstack:3`` service
# container in backend-ci.yml resolves to this same index today.
LOCALSTACK_IMAGE = "localstack/localstack@sha256:b279c01f4cfb8f985a482e4014cabc1e2697b9d7a6c8c8db2e40f4d9f93687c7"
LOCALSTACK_EDGE_PORT = 4566
LOCALSTACK_STARTUP_TIMEOUT_SECONDS = 120
# LocalStack accepts any static credentials; these are placeholders, not secrets.
S3_ACCESS_KEY_ID = "test"
S3_SECRET_ACCESS_KEY = "test"  # pragma: allowlist secret
S3_REGION = "us-east-1"


def _docker_available() -> bool:
    """Return True if the local Docker daemon is reachable.

    testcontainers raises DockerException at fixture setup if the
    daemon isn't running, which in CI/dev without Docker turns into a
    hard ERROR rather than a clean skip. This probes the socket
    up-front so the whole module can skip cleanly.
    """
    try:
        import docker  # type: ignore[import-untyped]

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _docker_available(),
        reason="Docker daemon not reachable — skipping testcontainers S3 integration",
    ),
]


def _s3_is_ready(body: str) -> bool:
    """Return True once LocalStack's health report lists S3 as usable.

    Readiness is decided by the ``services.s3`` state in the
    ``/_localstack/health`` body, not by the status code alone: S3 must be
    ``available`` (loaded lazily on first request) or ``running``.
    """
    try:
        report = json.loads(body)
    except ValueError:
        return False
    services = report.get("services") if isinstance(report, dict) else None
    return isinstance(services, dict) and services.get("s3") in {"available", "running"}


@pytest.fixture(scope="module")
def localstack_s3_container():
    """Start LocalStack with only S3 enabled and wait until S3 is ready."""
    # Wait on the health endpoint alone. LocalStack logs "Ready." a moment
    # before its edge port answers, so the log line is not sufficient, and a
    # composite wait would give each step its own timeout (twice the bound).
    # SKIP_SSL_CERT_DOWNLOAD and DISABLE_EVENTS stop LocalStack's outbound
    # calls at startup (TLS certificate fetch, analytics); the test uses
    # plain HTTP, so the fixture needs no network beyond the image pull.
    container = (
        DockerContainer(LOCALSTACK_IMAGE)
        .with_env("SERVICES", "s3")
        .with_env("SKIP_SSL_CERT_DOWNLOAD", "1")
        .with_env("DISABLE_EVENTS", "1")
        .with_exposed_ports(LOCALSTACK_EDGE_PORT)
        .waiting_for(
            HttpWaitStrategy(LOCALSTACK_EDGE_PORT, "/_localstack/health")
            .for_response_predicate(_s3_is_ready)
            .with_startup_timeout(LOCALSTACK_STARTUP_TIMEOUT_SECONDS)
        )
    )

    with container as localstack:
        yield localstack


@pytest.fixture
def s3_client(localstack_s3_container):
    """Provide a boto3 S3 client pointing to the test container."""
    host = localstack_s3_container.get_container_host_ip()
    port = localstack_s3_container.get_exposed_port(LOCALSTACK_EDGE_PORT)
    return boto3.client(
        "s3",
        endpoint_url=f"http://{host}:{port}",
        aws_access_key_id=S3_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SECRET_ACCESS_KEY,
        region_name=S3_REGION,
        config=Config(s3={"addressing_style": "path"}),
    )


def test_s3_ingestion_storage(s3_client):
    """
    Verify that we can store and retrieve raw ingestion data through a real S3 API.
    """
    bucket_name = "reg-engine-raw-data-test"
    s3_client.create_bucket(Bucket=bucket_name)

    test_content = b"Sample regulatory document text"
    test_key = "ingest/2026/test-doc.txt"

    # Store
    s3_client.put_object(Bucket=bucket_name, Key=test_key, Body=test_content)

    # Retrieve
    response = s3_client.get_object(Bucket=bucket_name, Key=test_key)
    retrieved_content = response["Body"].read()

    assert retrieved_content == test_content
