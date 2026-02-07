from typing import Iterable

from neo4j import Driver

# Simple heuristic: codes like "US-CA" belong under parent "US".
# For deeper hierarchies like "US-CA-SF", parent is "US-CA".


def parent_code_for(code: str) -> str | None:
    if not code:
        return None
    if "-" not in code:
        return None
    parts = code.split("-")
    if len(parts) <= 1:
        return None
    return "-".join(parts[:-1])


def build_jurisdiction_hierarchy(driver: Driver, codes: Iterable[str]) -> None:
    """
    Given an iterable of jurisdiction codes, ensure nodes exist and create
    CONTAINS edges from parent -> child based on code segmentation.

    Idempotent: uses MERGE for nodes and relationships.
    """
    with driver.session() as session:
        for code in set(codes):
            if not code:
                continue
            parent = parent_code_for(code)
            # Ensure the child node exists
            session.run(
                "MERGE (j:Jurisdiction {code: $code})",
                code=code,
            )
            if parent:
                session.run(
                    """
                    MERGE (p:Jurisdiction {code: $parent})
                    MERGE (c:Jurisdiction {code: $child})
                    MERGE (p)-[:CONTAINS]->(c)
                    """,
                    parent=parent,
                    child=code,
                )
