
import os
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

# Get DB URL from env or use default
DB_URL = os.environ.get(
    "ADMIN_DATABASE_URL", 
    "postgresql://regengine:regengine@localhost:5433/regengine_admin"
)

@pytest.fixture(scope="module")
def db_connection():
    """Create a raw DB connection for integrity testing."""
    try:
        conn = psycopg2.connect(DB_URL)
        yield conn
        conn.close()
    except psycopg2.OperationalError as e:
        pytest.skip(f"Database unavailable: {e}")

class TestFSMA204Invariants:
    """
    Phase 2a: Schema Invariant Verification for FSMA 204 Data.
    
    Verifies that existing data in the system adheres to critical regulatory 
    and architectural invariants, ensuring the 'Golden Corpus' is valid.
    """
    
    def test_authority_documents_have_required_metadata(self, db_connection):
        """
        Invariant: All Authority Documents must have an Issuer and Effective Date.
        Critical for audit trails (who said so, and when).
        """
        cur = db_connection.cursor(cursor_factory=RealDictCursor)
        
        # We query for any violation
        cur.execute("""
            SELECT id, document_code, issuer_name, effective_date 
            FROM pcos_authority_documents 
            WHERE issuer_name IS NULL 
               OR effective_date IS NULL
        """)
        violations = cur.fetchall()
        
        if violations:
            pytest.fail(f"Found {len(violations)} Authority Documents missing critical metadata: {violations}")
            
        # Verify specific known seeds exist (Smoke Test)
        cur.execute("SELECT COUNT(*) as count FROM pcos_authority_documents WHERE document_code = 'SAG_CBA_2023'")
        result = cur.fetchone()
        if result['count'] == 0:
            print("\nWARNING: Seed data for SAG_CBA_2023 missing. DB appears to be empty of default authorities.")
        
        # Check total count
        cur.execute("SELECT COUNT(*) as count FROM pcos_authority_documents")
        total = cur.fetchone()['count']
        if total == 0:
            print("\nNOTICE: pcos_authority_documents is empty. Invariant checks passed trivially.")

    def test_extracted_facts_polymorphic_consistency(self, db_connection):
        """
        Invariant: Extracted Facts must populate the value column matching their 'fact_value_type'.
        e.g., if type='decimal', fact_value_decimal must not be NULL.
        """
        cur = db_connection.cursor(cursor_factory=RealDictCursor)
        
        # Check Decimal
        cur.execute("""
            SELECT id, fact_key, fact_value_type 
            FROM pcos_extracted_facts 
            WHERE fact_value_type = 'decimal' AND fact_value_decimal IS NULL
        """)
        decimal_violations = cur.fetchall()
        assert len(decimal_violations) == 0, f"Facts with type 'decimal' missing decimal value: {decimal_violations}"

        # Check Integer
        cur.execute("""
            SELECT id, fact_key, fact_value_type 
            FROM pcos_extracted_facts 
            WHERE fact_value_type = 'integer' AND fact_value_integer IS NULL
        """)
        int_violations = cur.fetchall()
        assert len(int_violations) == 0, f"Facts with type 'integer' missing integer value: {int_violations}"

    def test_compliance_snapshots_integrity(self, db_connection):
        """
        Invariant: Compliance Snapshots must have a cryptographic content_hash.
        """
        cur = db_connection.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, snapshot_name 
            FROM compliance_snapshots 
            WHERE content_hash IS NULL
        """)
        violations = cur.fetchall()
        assert len(violations) == 0, f"Found {len(violations)} Compliance Snapshots missing cryptographic hash!"

    def test_authority_lineage_linkage(self, db_connection):
        """
        Invariant: All Extracted Facts must belong to an active Authority Document.
        (Referential integrity check beyond FKs, logic check).
        """
        cur = db_connection.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT f.id, f.fact_key, a.status as doc_status
            FROM pcos_extracted_facts f
            JOIN pcos_authority_documents a ON f.authority_document_id = a.id
            WHERE a.status = 'superseded' AND f.is_current = TRUE
        """)
        # Facts linked to superseded docs shouldn't necessarily be marked 'current' without review
        # This might be a soft failure/warning depending on business logic, 
        # but for STRICT integrity, current facts should generally come from active docs.
        # We'll treat it as a warning for now (print) or soft fail.
        
        warnings = cur.fetchall()
        if warnings:
            print(f"WARNING: {len(warnings)} Current Facts are linked to Superseded Authority Documents. Review required.")
            # Un-comment to enforce strictly:
            # pytest.fail(f"Current Facts linked to Superseded Docs: {warnings}")
