
import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:8002"  # Ingestion service default port
API_KEY = "admin"  # Updated to 'admin' base on .env suggestion

def test_ingest_url(url="https://www.example.com", source_system="test_script"):
    endpoint = f"{BASE_URL}/v1/ingest/url"
    payload = {
        "url": url,
        "source_system": source_system
    }
    headers = {
        "X-RegEngine-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    print(f"Testing URL ingestion: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        try:
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        except:
            print(f"Response Text: {response.text}")
            
        if response.status_code == 200:
            print("SUCCESS: Ingestion successful")
        else:
            print("FAILURE: Ingestion failed")
            
    except Exception as e:
        print(f"ERROR: Could not connect to service. {e}")

if __name__ == "__main__":
    url_to_test = sys.argv[1] if len(sys.argv) > 1 else "https://www.google.com"
    test_ingest_url(url_to_test)
