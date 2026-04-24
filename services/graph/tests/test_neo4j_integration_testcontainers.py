
import os
import pytest
from neo4j import GraphDatabase

# Skip testcontainers tests in CI — CI has its own Neo4j service container on port 7687
# which conflicts with testcontainers trying to spin up another instance
_IN_CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"


@pytest.fixture(scope="session")
def neo4j_container():
    """Start a real Neo4j container for graph integration testing."""
    if _IN_CI:
        pytest.skip("Skipping testcontainers in CI (uses CI service container instead)")
    from testcontainers.neo4j import Neo4jContainer
    with Neo4jContainer("neo4j:5.24-community") as neo4j:
        yield neo4j

@pytest.fixture
def neo4j_driver(neo4j_container):
    """Provide a Neo4j driver pointing to the test container."""
    driver = neo4j_container.get_driver()
    yield driver
    driver.close()

def test_neo4j_traceability_query(neo4j_driver):
    """
    Verify that we can run complex regulatory traceability queries in real Neo4j.
    """
    with neo4j_driver.session() as session:
        # Create a simple supply chain trace
        session.run("""
            CREATE (f:Facility {name: 'Farm A', gln: '123'})
            CREATE (d:Distributor {name: 'Distributor B', gln: '456'})
            CREATE (r:Retailer {name: 'Store C', gln: '789'})
            CREATE (f)-[:SHIPPED_TO {date: '2026-02-01'}]->(d)
            CREATE (d)-[:SHIPPED_TO {date: '2026-02-02'}]->(r)
        """)
        
        # Run a "one-up/one-down" traceability query
        result = session.run("""
            MATCH (r:Retailer {gln: '789'})<-[:SHIPPED_TO]-(d)<-[:SHIPPED_TO]-(f)
            RETURN f.name as source_farm, d.name as distributor
        """)
        
        record = result.single()
        assert record["source_farm"] == "Farm A"
        assert record["distributor"] == "Distributor B"
        print("✅ Neo4j traceability query verified with Testcontainers")
