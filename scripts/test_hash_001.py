import requests
import hashlib
import uuid
import json
import os

# Configuration
INGEST_URL = "http://localhost:8002/v1/ingest/url"
API_KEY = os.getenv("REGENGINE_API_KEY", "")
S3_ENDPOINT = "http://localhost:4566"

def test_hash_integrity():
    if not API_KEY:
        print("Set REGENGINE_API_KEY before running this script.")
        return

    # 1. Generate unique URL to ensure new ingestion
    unique_id = str(uuid.uuid4())
    test_url = f"https://httpbin.org/get?unique={unique_id}"
    
    print(f"Ingesting unique URL: {test_url}")
    
    payload = {
        "url": test_url,
        "source_system": "test-matrix",
        "vertical": "test"
    }
    
    headers = {
        "X-RegEngine-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    response = requests.post(INGEST_URL, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"Ingestion failed: {response.status_code} - {response.text}")
        return

    data = response.json()
    returned_hash = data.get("content_sha256")
    raw_s3_path = data.get("raw_s3_path")
    
    print(f"Ingestion successful.")
    print(f"Returned Hash: {returned_hash}")
    print(f"Raw S3 Path: {raw_s3_path}")
    
    if "skipped://duplicate" in raw_s3_path:
        print("FAIL: Item was surprisingly marked as duplicate.")
        return

    # 2. Download from S3
    # raw_s3_path looks like s3://bucket/key
    parts = raw_s3_path.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    key = parts[1]
    
    download_url = f"{S3_ENDPOINT}/{bucket}/{key}"
    print(f"Downloading from: {download_url}")
    
    dl_response = requests.get(download_url)
    if dl_response.status_code != 200:
        print(f"Download failed: {dl_response.status_code}")
        # Try once more with a bucket listing check
        return

    content = dl_response.content
    
    # 3. Verify Hash
    computed_hash = hashlib.sha256(content).hexdigest()
    print(f"Computed Hash: {computed_hash}")
    
    if computed_hash == returned_hash:
        print("HASH-001 PASS: Cryptographic hash matches content stored in S3.")
    else:
        print("HASH-001 FAIL: Hash mismatch!")
        print(f"Expected: {returned_hash}")
        print(f"Actual:   {computed_hash}")

if __name__ == "__main__":
    test_hash_integrity()
