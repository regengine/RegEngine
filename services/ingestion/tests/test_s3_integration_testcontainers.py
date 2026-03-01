import pytest
from testcontainers.core.container import DockerContainer
import boto3

@pytest.fixture(scope="session")
def minio_container():
    """Start a real MinIO container for S3 integration testing."""
    container = DockerContainer("minio/minio:RELEASE.2024-01-16T16-07-38Z")
    container.with_env("MINIO_ROOT_USER", "minio")
    container.with_env("MINIO_ROOT_PASSWORD", "minio123")
    container.with_command("server /data --console-address :9001")
    container.with_exposed_ports(9000, 9001)

    with container as minio:
        yield minio

@pytest.fixture
def s3_client(minio_container):
    """Provide a boto3 S3 client pointing to the test container."""
    endpoint_url = f"http://{minio_container.get_container_host_ip()}:{minio_container.get_exposed_port(9000)}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id="minio",
        aws_secret_access_key="minio123",
        region_name="us-east-1"
    )

def test_s3_ingestion_storage(s3_client):
    """
    Verify that we can store and retrieve raw ingestion data using real S3.
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
    print("✅ S3 integration verified with MinIO")
