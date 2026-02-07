#!/bin/bash
# scripts/create_neo4j_indexes.sh
# Creates production indexes for FSMA 204 Graph performance

echo "Creating Neo4j Indexes..."

# Wait for Neo4j to be ready
until curl -s http://localhost:7474 > /dev/null; do
    echo "Waiting for Neo4j..."
    sleep 5
done

# Run Cypher commands via Docker exec
docker exec neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD} <<EOF
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
