
import pytest
from testcontainers.neo4j import Neo4jContainer
from neo4j import GraphDatabase
import uuid

@pytest.fixture(scope="session")
def neo4j_container():
    with Neo4jContainer("neo4j:5.24-community") as neo4j:
        yield neo4j

@pytest.fixture
def neo4j_driver(neo4j_container):
    driver = GraphDatabase.driver(
        neo4j_container.get_connection_url(),
        auth=("neo4j", "password")
    )
    yield driver
    driver.close()

def test_compliance_overlap_analysis(neo4j_driver):
    """
    Verify that we can detect overlapping regulatory obligations 
    across different jurisdictions using real Neo4j.
    """
    with neo4j_driver.session() as session:
        # Create overlapping regulations
        session.run("""
            CREATE (r1:Regulation {id: 'FSMA_204', name: 'Food Safety', jurisdiction: 'US'})
            CREATE (r2:Regulation {id: 'EU_178', name: 'Food Law', jurisdiction: 'EU'})
            CREATE (o1:Obligation {id: 'Traceability', description: 'One-up one-down'})
            CREATE (r1)-[:HAS_OBLIGATION]->(o1)
            CREATE (r2)-[:HAS_OBLIGATION]->(o1)
        """)
        
        # Query for cross-jurisdictional overlaps
        result = session.run("""
            MATCH (o:Obligation)<-[:HAS_OBLIGATION]-(r:Regulation)
            WITH o, collect(r. jurisdiction) as jurisdictions, count(r) as reg_count
            WHERE reg_count > 1
            RETURN o.id as obligation, jurisdictions
        """)
        
        record = result.single()
        assert record["obligation"] == "Traceability"
        assert "US" in record["jurisdictions"]
        assert "EU" in record["jurisdictions"]
        print("✅ Compliance overlap analysis verified with Neo4j Testcontainers")
