import boto3
import json
import hashlib
import psycopg
from psycopg.rows import dict_row

# Config - Internal Docker names
S3_CONFIG = {
    "endpoint_url": "http://minio:9000",
    "aws_access_key_id": "minio",
    "aws_secret_access_key": "minio123",
    "region_name": "us-east-1"
}
BUCKET = "reg-engine-processed-data-dev"
DB_CONFIG = {
    "host": "postgres",
    "port": 5432,
    "database": "regengine_admin",
    "user": "regengine",
    "password": "regengine"
}

# Targeted hash for a known successful ingestion
TARGET_HASH = "fd8e532cadeb3438ec31c9df867466977d2696722d5e93b43498a61c8c53c20c"

def test_s3_integrity():
    print(f"Executing HASH-002: S3 Normalized Content Tamper Test (Target: {TARGET_HASH[:12]})")
    print("---------------------------------------------------------")
    
    s3 = boto3.client("s3", **S3_CONFIG)
    
    try:
        # 1. Selection
        conn = psycopg.connect(**DB_CONFIG)
        cur = conn.cursor(row_factory=dict_row)
        cur.execute("SELECT id, title, content_sha256, storage_key FROM ingestion.documents WHERE content_sha256 = %s;", (TARGET_HASH,))
        doc = cur.fetchone()
        if not doc:
            print(f"FAIL: Document with hash {TARGET_HASH} not found.")
            return
            
        doc_id = doc['id']
        expected_hash = doc['content_sha256']
        s3_url = doc['storage_key']
        key = s3_url.replace(f"s3://{BUCKET}/", "")
        
        print(f"Testing Document: {doc['title']} ({doc_id})")
        print(f"Database content_sha256: {expected_hash}")
        
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
        
        # 4. Verification Check
        print("Running Baseline Integrity Check...")
        response = s3.get_object(Bucket=BUCKET, Key=key)
        current_body = response['Body'].read()
        computed_hash = hashlib.sha256(current_body).hexdigest()
        
        print(f"Computed SHA-256 of S3 object: {computed_hash}")
        
        if computed_hash != expected_hash:
            print("HASH-002 PASS: Cryptographic integrity violation DETECTED (Flagged).")
            print(f"Verification: DB Hash ({expected_hash}) != S3 Hash ({computed_hash})")
        else:
            print("HASH-002 FAIL: Hash still matches? (Wait, did the hash ignore metadata?)")
            
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_s3_integrity()
