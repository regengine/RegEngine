#!/bin/bash
# scripts/create_neo4j_indexes.sh
# Creates production indexes for FSMA 204 Graph performance

echo "Creating Neo4j Indexes..."

# Wait for Neo4j to be ready
until curl -s http://localhost:7474 > /dev/null; do
    echo "Waiting for Neo4j..."
    sleep 5
done

# Run Cypher commands via Docker exec.
# Never pass the password with -p: it lands in the host process table where
# anyone on the box can read it. cypher-shell also accepts NEO4J_USERNAME /
# NEO4J_PASSWORD from the environment, so hand them over in a 0600 env file
# instead of argv (Pattern 11: secrets from env, never argv).
if [[ -z "${NEO4J_PASSWORD:-}" ]]; then
    echo "ERROR: set NEO4J_PASSWORD in the environment" >&2
    exit 2
fi
ENV_FILE="$(mktemp)"
chmod 600 "$ENV_FILE"
trap 'rm -f "$ENV_FILE"' EXIT
printf 'NEO4J_USERNAME=%s\nNEO4J_PASSWORD=%s\n' "neo4j" "$NEO4J_PASSWORD" > "$ENV_FILE"
docker exec --env-file "$ENV_FILE" neo4j cypher-shell -u neo4j <<EOF
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
