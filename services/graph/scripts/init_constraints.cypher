// Neo4j Constraint Initialization Script
// This script creates unique constraints for the RegEngine graph database
// to ensure data integrity at the database level.

// Create unique constraint for Lot nodes
// Ensures that the combination of TLC (Traceability Lot Code) and tenant_id is unique
// This prevents duplicate lots from being created within the same tenant
CREATE CONSTRAINT lot_tlc_tenant_unique IF NOT EXISTS
FOR (l:Lot) REQUIRE (l.tlc, l.tenant_id) IS UNIQUE;

// Additional constraints can be added here as needed
// Examples:
// CREATE CONSTRAINT facility_gln_tenant_unique IF NOT EXISTS
// FOR (f:Facility) REQUIRE (f.gln, f.tenant_id) IS UNIQUE;
