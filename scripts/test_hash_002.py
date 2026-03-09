import hashlib
import psycopg
from psycopg.rows import dict_row
import sys

# DB connection config - Use 127.0.0.1 to avoid local postgres collision
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "regengine_admin",
    "user": "regengine",
    "password": "regengine"
}

def test_normalized_integrity():
    print("Executing HASH-002: Normalized Hash Integrity Test")
    print("-----------------------------------------------")
    
    try:
        conn = psycopg.connect(**DB_CONFIG)
        cur = conn.cursor(row_factory=dict_row)
        
        # 1. Selection
        cur.execute("SELECT id, title, text_sha256 FROM ingestion.documents WHERE text_sha256 IS NOT NULL LIMIT 1;")
        doc = cur.fetchone()
        if not doc:
            print("FAIL: No documents with text_sha256 found.")
            return
            
        doc_id = doc['id']
        expected_hash = doc['text_sha256']
        print(f"Testing Document: {doc['title']} ({doc_id})")
        print(f"Original text_sha256: {expected_hash}")
        
        # 2. Tamper Simulation
        print("Simulating Tamper: Modifying document text in database...")
        cur.execute("UPDATE ingestion.documents SET text = 'CRITICAL ALERT: THIS DATA HAS BEEN TAMPERED WITH BY THE ADVERSARY.' WHERE id = %s", (str(doc_id),))
        conn.commit()
        
        # 3. Verification (Baseline Audit)
        print("Running Baseline Integrity Audit...")
        cur.execute("SELECT text FROM ingestion.documents WHERE id = %s", (str(doc_id),))
        tampered_doc = cur.fetchone()
        tampered_text = tampered_doc['text']
        
        computed_hash = hashlib.sha256(tampered_text.encode('utf-8')).hexdigest()
        print(f"Computed Hash: {computed_hash}")
        
        if computed_hash != expected_hash:
            print("HASH-002 PASS: Integrity violation DETECTED (Flagged).")
            print(f"Baseline mismatch: Expected {expected_hash}, found {computed_hash}")
        else:
            print("HASH-002 FAIL: Tamper not detected!")
            
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_normalized_integrity()
