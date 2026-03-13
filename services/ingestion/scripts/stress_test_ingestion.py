import asyncio
import aiohttp
import time
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("stress_test")

API_KEY = os.getenv("REGENGINE_API_KEY", "")
INGESTION_URL = os.getenv("INGESTION_API_URL", "http://localhost:8002/v1/ingest/url")

TEST_VECTORS = [
    {
        "name": "Vector A: Heavy eCFR XML (Structured Complexity)",
        "url": "https://www.ecfr.gov/api/versioner/v1/full/2024-01-01/title-21.xml?chapter=I&subchapter=A&part=11",
        "vertical": "fsma"
    },
    {
        "name": "Vector B: Large FDA Guidance Document (Unstructured PDF)",
        "url": "https://www.fda.gov/media/145048/download",
        "vertical": "fsma"
    },
    {
        "name": "Vector C: Federal Register API (JSON/HTML Mix)",
        "url": "https://www.federalregister.gov/api/v1/documents/2022-25183.json",
        "vertical": "fsma"
    },
    {
        "name": "Vector D: Hostile / Invalid Content (Image File)",
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Example.jpg",
        "vertical": "general"
    },
    {
        "name": "Vector E: Non-Existent Endpoint (404/DNS Error)",
        "url": "https://this-url-definitely-does-not-exist-regengine.gov/404",
        "vertical": "general"
    },
    {
        "name": "Vector F: Large HTML Document",
        "url": "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods",
        "vertical": "fsma"
    }
]

async def send_ingest_request(session, vector):
    logger.info(f"Starting test: {vector['name']}")
    start_time = time.time()
    
    headers = {
        "Content-Type": "application/json",
        "X-RegEngine-API-Key": API_KEY
    }
    payload = {
        "url": vector["url"],
        "vertical": vector["vertical"],
        "source_system": "stress_test_harness"
    }

    try:
        async with session.post(INGESTION_URL, json=payload, headers=headers, timeout=60) as response:
            duration = time.time() - start_time
            response_text = await response.text()
            
            try:
                response_json = json.loads(response_text)
            except json.JSONDecodeError:
                response_json = {"raw_text": response_text[:200] + "..."}
                
            status_code = response.status
            
            if status_code == 200:
                logger.info(f"✅ SUCCESS: {vector['name']} in {duration:.2f}s")
                # Print just the metadata structure, not the whole massive JSON
                if "normalized_s3_path" in response_json:
                    logger.info(f"   Stored at: {response_json['normalized_s3_path']}")
            elif status_code in [400, 422, 404]:
                logger.warning(f"⚠️ GRACEFUL FAILURE: {vector['name']} failed correctly with {status_code} in {duration:.2f}s: {response_json}")
            else:
                logger.error(f"❌ FATAL ERROR: {vector['name']} returned {status_code} in {duration:.2f}s: {response_json}")
                
            return {
                "vector": vector["name"],
                "status": status_code,
                "duration": duration,
                "response": response_json
            }
            
    except asyncio.TimeoutError:
        duration = time.time() - start_time
        logger.error(f"❌ TIMEOUT: {vector['name']} timed out after {duration:.2f}s")
        return {"vector": vector["name"], "status": "timeout", "duration": duration}
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ CRASH: {vector['name']} crashed harness: {str(e)}")
        return {"vector": vector["name"], "status": "crash", "duration": duration, "error": str(e)}

async def main():
    if not API_KEY:
        raise RuntimeError("Set REGENGINE_API_KEY before running stress test.")

    logger.info("Initializing RegEngine Ingestion Stress Test")
    logger.info("="*50)
    
    async with aiohttp.ClientSession() as session:
        # Run sequentially first to isolate timeouts/crashes
        results = []
        for vector in TEST_VECTORS:
            res = await send_ingest_request(session, vector)
            results.append(res)
            
        logger.info("="*50)
        logger.info("Test Summary:")
        for res in results:
            status = res.get('status')
            icon = "✅" if status == 200 else ("⚠️" if status in [400, 422, 404] else "❌")
            logger.info(f"{icon} {res['vector']}: Status {status} ({res['duration']:.2f}s)")

if __name__ == "__main__":
    asyncio.run(main())
