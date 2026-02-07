// ============================================================================
// RegEngine Database Constraints - Production Ready Schema
// ============================================================================
// This script establishes data integrity constraints for the Neo4j database.
// Execute this script during initial deployment or migrations.
//
// Usage:
//   1. Via Neo4j Browser: Copy and paste into the query editor
//   2. Via cypher-shell: cypher-shell -f init_db_constraints.cypher
//   3. Via Python/API: Run as part of application startup
//
// ============================================================================

// **Task 3.1: Apply Unique Constraint for Lot TLC + Tenant**
// Guarantees that each combination of (tlc, tenant_id) is unique across the database.
// This prevents duplicate lot creation and ensures data integrity at the database level.
CREATE CONSTRAINT lot_tlc_tenant_unique IF NOT EXISTS
FOR (l:Lot) REQUIRE (l.tlc, l.tenant_id) IS UNIQUE;

// Additional Production-Ready Constraints (Optional but Recommended)

// Ensure Tenant IDs are unique
CREATE CONSTRAINT tenant_id_unique IF NOT EXISTS
FOR (t:Tenant) REQUIRE t.id IS UNIQUE;

// Ensure Facility GLNs are unique per tenant
CREATE CONSTRAINT facility_gln_tenant_unique IF NOT EXISTS
FOR (f:Facility) REQUIRE (f.gln, f.tenant_id) IS UNIQUE;

// ============================================================================
// Indexes for Performance (Optional)
// ============================================================================

// Index on Lot.gtin for faster product lookups
CREATE INDEX lot_gtin_index IF NOT EXISTS FOR (l:Lot) ON (l.gtin);

// Index on Lot.created_at for time-based queries
CREATE INDEX lot_created_at_index IF NOT EXISTS FOR (l:Lot) ON (l.created_at);

// ============================================================================
// Verification Query (Run after applying constraints)
// ============================================================================
// CALL db.constraints();
// CALL db.indexes();
