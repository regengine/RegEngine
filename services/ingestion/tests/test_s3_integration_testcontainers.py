
import pytest
from testcontainers.localstack import LocalStackContainer
import boto3
import os

@pytest.fixture(scope="session")
def localstack_container():
    """Start a real LocalStack container for S3 integration testing."""
    with LocalStackContainer("localstack/localstack:3") as localstack:
        yield localstack

@pytest.fixture
def s3_client(localstack_container):
    """Provide a boto3 S3 client pointing to the test container."""
    return boto3.client(
        "s3",
        endpoint_url=localstack_container.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
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
    print("✅ S3 integration verified with LocalStack")
