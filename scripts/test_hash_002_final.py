import boto3
import json
import hashlib
import psycopg
from psycopg.rows import dict_row

# Config
S3_CONFIG = {
    "endpoint_url": "http://localhost:4566",
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
    "region_name": "us-east-1"
}
BUCKET = "reg-engine-processed-data-dev"
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "regengine_admin",
    "user": "regengine",
    "password": "regengine"
}

def test_s3_integrity():
    print("Executing HASH-002: S3 Normalized Content Tamper Test")
    print("--------------------------------------------------")
    
    s3 = boto3.client("s3", **S3_CONFIG)
    
    # 1. Identify document in DB
    conn = psycopg.connect(**DB_CONFIG)
    cur = conn.cursor(row_factory=dict_row)
    cur.execute("SELECT id, title, content_sha256, storage_key FROM ingestion.documents WHERE length(content_sha256) > 0 LIMIT 1;")
    doc = cur.fetchone()
    if not doc:
        print("FAIL: No documents found.")
        return
        
    doc_id = doc['id']
    expected_hash = doc['content_sha256']
    # Storage key in DB is s3://bucket/key
    s3_url = doc['storage_key']
    key = s3_url.replace(f"s3://{BUCKET}/", "")
    
    print(f"Testing Document: {doc['title']} ({doc_id})")
    print(f"Database content_sha256: {expected_hash}")
    print(f"S3 Key: {key}")
    
    # 2. Download and Tamper
    print("Downloading normalized content from S3...")
    response = s3.get_object(Bucket=BUCKET, Key=key)
    body = response['Body'].read().decode('utf-8')
    data = json.loads(body)
    
    # Tamper with the content
    print("Simulating Tamper: Modifying parsed text in S3 object...")
    data['parsed_text'] = "ADVERSARY OVERWRITE: CLASSIFIED CONTENT HAS BEEN EXFILTRATED."
    tampered_body = json.dumps(data).encode('utf-8')
    
    # 3. Upload Tampered Content
    s3.put_object(Bucket=BUCKET, Key=key, Body=tampered_body)
    print("Tampered content uploaded to S3.")
    
    # 4. Verification Check (Baseline Integrity Scraper simulation)
    print("Running Baseline Integrity Check...")
    response = s3.get_object(Bucket=BUCKET, Key=key)
    current_body = response['Body'].read()
    computed_hash = hashlib.sha256(current_body).hexdigest()
    
    print(f"Computed SHA-256 of S3 object: {computed_hash}")
    
    if computed_hash != expected_hash:
        print("HASH-002 PASS: Cryptographic integrity violation DETECTED (Flagged).")
        print(f"Verification: DB Hash ({expected_hash}) != S3 Hash ({computed_hash})")
    else:
        print("HASH-002 FAIL: Hash still matches? (Wait, did I tamper properly?)")
        
    conn.close()

if __name__ == "__main__":
    test_s3_integrity()
