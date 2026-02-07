"""Load test script for ingestion service."""

import time
import requests
import uuid
import concurrent.futures

API_URL = "http://localhost:8000/v1/ingest/url"
API_KEY = "admin"

def ingest_document(i):
    # Use a dummy but unique URL per request to avoid some levels of caching if any
    url = f"https://example.com/doc_{i}"
    payload = {
        "url": url,
        "vertical": "test_load",
        "source_system": f"load_test_{i}"
    }
    headers = {
        "X-RegEngine-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    start = time.perf_counter()
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        end = time.perf_counter()
        return response.status_code, end - start
    except Exception as e:
        return 500, str(e)

def run_load_test(count=50, concurrency=5):
    print(f"Starting load test: {count} docs, concurrency {concurrency}")
    
    results = []
    start_all = time.perf_counter()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(ingest_document, i) for i in range(count)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    end_all = time.perf_counter()
    
    success = [r for r in results if r[0] == 200]
    failures = [r for r in results if r[0] != 200]
    
    print(f"\n--- Load Test Results ---")
    print(f"Total time: {end_all - start_all:.2f}s")
    print(f"Total requests: {len(results)}")
    print(f"Successful: {len(success)}")
    print(f"Failed: {len(failures)}")
    
    if success:
        avg_time = sum(r[1] for r in success) / len(success)
        print(f"Average success time: {avg_time:.2f}s")
        
    if failures:
        print(f"Failures: {failures[:5]}...")

if __name__ == "__main__":
    # Ensure service is up before running
    try:
        run_load_test(count=20, concurrency=4)
    except Exception as e:
        print(f"Could not run load test: {e}")
