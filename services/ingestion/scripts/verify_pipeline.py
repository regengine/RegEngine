import os
import sys
import json
import psycopg
import boto3

def verify_pipeline():
    print("=== Pipeline Verification ===")

    db_password = os.getenv("REGENGINE_DB_PASSWORD", "")
    minio_key = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret = os.getenv("MINIO_SECRET_KEY", "")

    if not db_password:
        print("DB Error: set REGENGINE_DB_PASSWORD before running this script")
        return
    if not minio_key or not minio_secret:
        print("S3 Error: set MINIO_ACCESS_KEY and MINIO_SECRET_KEY before running this script")
        return
    
    # 1. Check PostgreSQL
    print("\n--- PostgreSQL: ingestion.documents ---")
    try:
        conn = psycopg.connect(
            host="localhost",
            port=5432,
            dbname="regengine_admin",
            user="regengine",
            password=db_password,
        )
        cur = conn.cursor()
        cur.execute("SELECT id, title, document_type, content_length FROM ingestion.documents ORDER BY fetch_timestamp DESC LIMIT 5;")
        rows = cur.fetchall()
        for row in rows:
            print(f"Doc: {row[1][:40]}... | Type: {row[2]} | Length: {row[3]}")
    except Exception as e:
        print(f"DB Error: {e}")

    # 2. Check object storage (MinIO)
    print("\n--- S3: Claim Check normalized-text/ ---")
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url="http://localhost:9000",
            aws_access_key_id=minio_key,
            aws_secret_access_key=minio_secret,
            region_name="us-east-1"
        )
        response = s3.list_objects_v2(Bucket="reg-engine-processed-data-dev", Prefix="normalized-text/")
        if 'Contents' in response:
            for obj in response['Contents']:
                print(f"Key: {obj['Key']} | Size: {obj['Size']} bytes")
        else:
            print("No Claim Check objects found.")
    except Exception as e:
        print(f"S3 Error: {e}")

if __name__ == "__main__":
    verify_pipeline()
