#!/bin/bash
# scripts/create_neo4j_indexes.sh
# Creates production indexes for FSMA 204 Graph performance

echo "Creating Neo4j Indexes..."

: "${NEO4J_PASSWORD:?Set NEO4J_PASSWORD before running this script}"
# Export so docker can pass it through by name (-e NEO4J_PASSWORD below).
# The value never appears in any process command line.
export NEO4J_PASSWORD

# Wait for Neo4j to be ready
until curl -s http://localhost:7474 > /dev/null; do
    echo "Waiting for Neo4j..."
    sleep 5
done

# Run Cypher commands via Docker exec. cypher-shell reads NEO4J_PASSWORD from
# the environment, so no secret is passed with -p on the command line.
docker exec -e NEO4J_PASSWORD neo4j cypher-shell -u neo4j <<EOF
// Traceability Indexes
CREATE INDEX trace_event_lot_code IF NOT EXISTS FOR (e:TraceEvent) ON (e.lot_code);
CREATE INDEX trace_event_date IF NOT EXISTS FOR (e:TraceEvent) ON (e.event_date);
CREATE INDEX trace_event_gln IF NOT EXISTS FOR (e:TraceEvent) ON (e.facility_gln);

// Facility Indexes
CREATE INDEX facility_gln IF NOT EXISTS FOR (f:Facility) ON (f.gln);
CREATE INDEX facility_tenant IF NOT EXISTS FOR (f:Facility) ON (f.tenant_id);

// Audit Indexes
CREATE INDEX audit_timestamp IF NOT EXISTS FOR (a:AuditLog) ON (a.timestamp);
CREATE INDEX audit_entity IF NOT EXISTS FOR (a:AuditLog) ON (a.entity_id);

// Compliance Indexes
CREATE INDEX compliance_doc_id IF NOT EXISTS FOR (c:ComplianceDoc) ON (c.document_id);
EOF

echo "Neo4j Indexes Created Successfully."
