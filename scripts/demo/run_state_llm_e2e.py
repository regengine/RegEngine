#!/usr/bin/env python3
import os
import argparse
import requests
import hashlib

from services.nlp.app.extractors.llm_extractor import LLMGenerativeExtractor, SimpleLLMClient
from services.nlp.app.text_loader import load_artifact
from services.nlp.app.s3_loader import load_s3_artifact
import uuid
from services.graph.app.hierarchy_builder import build_jurisdiction_hierarchy

class FakeLLMClient(SimpleLLMClient):
        def __init__(self):  # satisfy type checker by subclassing SimpleLLMClient
                super().__init__(model="fake")

        def generate_json(self, prompt: str) -> str:
                # Deterministic demo payload: NYDFS Part 500 24-hour notification
                return (
                        "[\n"
                        "  {\n"
                        "    \"provision_text\": \"24-hour notification required to the DFS Superintendent.\",\n"
                        "    \"obligation_type\": \"REPORTING\",\n"
                        "    \"confidence\": 0.95\n"
                        "  }\n"
                        "]\n"
                )


def parse_args():
    parser = argparse.ArgumentParser(description="Run LLM-first state ingestion E2E demo")
    parser.add_argument("--url", required=True, help="Source URL (e.g., NYDFS Part 500 PDF)")
    parser.add_argument("--jurisdiction", default="US-NY", help="Jurisdiction code, default US-NY")
    parser.add_argument("--ingestion_base", default=os.getenv("INGESTION_BASE", "http://localhost:8001"), help="Ingestion service base URL")
    parser.add_argument("--api_key", default=os.getenv("X_REGENGINE_API_KEY", "dev-key"), help="API key header value")
    parser.add_argument("--neo4j_uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j_user", default=os.getenv("NEO4J_USER", "neo4j"))
    # No default password - must be set via NEO4J_PASSWORD env var or --neo4j_password arg
    parser.add_argument("--neo4j_password", default=os.getenv("NEO4J_PASSWORD"), 
                        help="Neo4j password (required, set via env var NEO4J_PASSWORD or this arg)")
    return parser.parse_args()


def choose_route(jurisdiction: str) -> str:
    if jurisdiction == "US-NY":
        return "/v1/scrape/nydfs"
    if jurisdiction.startswith("US-CA"):
        return "/v1/scrape/cppa"
    return "/v1/scrape/nydfs"


def call_ingestion(ingestion_base: str, api_key: str, route: str, url: str, corr_id: str) -> dict:
    print(f"[ingestion] POST {ingestion_base}{route}?url={url}")
    resp = requests.post(
        f"{ingestion_base}{route}",
        params={"url": url},
        headers={"X-RegEngine-API-Key": api_key, "X-Request-ID": corr_id},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Ingestion failed: {resp.status_code} {resp.text}")
    event = resp.json()
    print(f"[ingestion] ok -> {event}")
    return event


def upsert_graph(jurisdiction: str, results: list, neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> None:
    if not results:
        return
    try:
        from neo4j import GraphDatabase  # type: ignore
    except Exception as e:
        print(f"[graph] neo4j driver not available: {e}")
        return
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        build_jurisdiction_hierarchy(driver, [jurisdiction])
        with driver.session() as session:
            for r in results:
                rd = r.model_dump() if hasattr(r, "model_dump") else dict(r)
                provision_text = rd.get("provision_text", "")
                obligation_type = rd.get("obligation_type", "UNKNOWN")
                confidence = rd.get("confidence", 0.0)
                pid = hashlib.sha256(f"{jurisdiction}|{provision_text}".encode("utf-8")).hexdigest()[:32]
                cypher = (
                    "MERGE (p:Provision {pid: $pid})\n"
                    "SET p.text = $text, p.obligation_type = $obligation_type, p.confidence = $confidence\n"
                    "WITH p\n"
                    "UNWIND $jurisdiction_codes AS code\n"
                    "MERGE (j:Jurisdiction {code: code})\n"
                    "MERGE (p)-[:APPLIES_TO]->(j)"
                )
                params = {
                    "pid": pid,
                    "text": provision_text,
                    "obligation_type": obligation_type,
                    "confidence": confidence,
                    "jurisdiction_codes": [jurisdiction],
                }
                session.run(cypher, params).consume()
                print(f"[graph] upserted Provision pid={pid} -> APPLIES_TO {jurisdiction}")
    finally:
        driver.close()


def main():
    args = parse_args()

    route = choose_route(args.jurisdiction)
    corr_id = str(uuid.uuid4())
    try:
        event = call_ingestion(args.ingestion_base, args.api_key, route, args.url, corr_id)
    except Exception as e:
        print(str(e))
        return

    # Load artifact text (demo supports http(s) URLs)
    s3_uri = event.get("s3_uri")
    src_url = event.get("source_url") or args.url
    try:
        if s3_uri:
            text = load_s3_artifact(s3_uri)
        else:
            text = load_artifact(src_url)
    except Exception:
        # Fallback to embedded key sentence for demo validation
        text = "Section 500.17: 24-hour notification required to the DFS Superintendent."

    extractor = LLMGenerativeExtractor()
    extractor.client = FakeLLMClient()  # inject fake client
    results = extractor.extract(text, args.jurisdiction, correlation_id=corr_id)

    print("[nlp] extracted obligations:")
    for r in results:
        rd = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        print({"provision_text": rd.get("provision_text"), "obligation_type": rd.get("obligation_type"), "confidence": rd.get("confidence")})

    # Graph upsert: create Provision, link to Jurisdiction via APPLIES_TO, ensure BELONGS_TO hierarchy
    upsert_graph(args.jurisdiction, results, args.neo4j_uri, args.neo4j_user, args.neo4j_password)

if __name__ == "__main__":
    main()
