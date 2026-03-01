import os
import sys
import json
import psycopg2
import boto3

def verify_pipeline():
    print("=== Pipeline Verification ===")
    
    # 1. Check PostgreSQL
    print("\n--- PostgreSQL: ingestion.documents ---")
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="regengine_admin",
            user="regengine",
            password="regengine_password"
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
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin123",
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
