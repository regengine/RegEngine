#!/usr/bin/env python3
import os
import sys

from app.hierarchy_builder import build_jurisdiction_hierarchy
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
# No default password - must be set via NEO4J_PASSWORD environment variable
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    print("ERROR: NEO4J_PASSWORD environment variable must be set", file=sys.stderr)
    sys.exit(1)


def fetch_all_jurisdiction_codes(driver):
    with driver.session() as session:
        result = session.run("MATCH (j:Jurisdiction) RETURN DISTINCT j.code AS code")
        return [record["code"] for record in result]


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        codes = fetch_all_jurisdiction_codes(driver)
        build_jurisdiction_hierarchy(driver, codes)
        print(f"Built hierarchy for {len(set(codes))} jurisdiction codes.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
