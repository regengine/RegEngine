// ============================================================================
// RegEngine Core Regulatory Schema - Production Ready Integrity
// ============================================================================
// This script establishes the foundational constraints and indexes for the 
// Regulatory Knowledge Graph.
// ============================================================================

// --- CONSTRAINTS ---

// 1. Framework Uniqueness
// Ensures framework names are unique to prevent overlapping definitions.
CREATE CONSTRAINT framework_name_unique IF NOT EXISTS
FOR (f:Framework) REQUIRE f.name IS UNIQUE;

// 2. Control Uniqueness
// Ensures control IDs (per framework name prefix) are unique.
CREATE CONSTRAINT control_id_unique IF NOT EXISTS
FOR (c:Control) REQUIRE c.control_id IS UNIQUE;

// 3. Jurisdiction Uniqueness
// Unique code for each jurisdiction (Federal, State, International).
CREATE CONSTRAINT jurisdiction_code_unique IF NOT EXISTS
FOR (j:Jurisdiction) REQUIRE j.code IS UNIQUE;

// 4. Document Uniqueness
// Track unique documents by their source ID and content hash.
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT document_hash_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.hash IS UNIQUE;

// 5. Concept Uniqueness
// Unified terminology Concept mapping.
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS UNIQUE;


// --- INDEXES ---

// 1. Semantic Search & Lookup Performance
CREATE INDEX control_requirement_index IF NOT EXISTS 
FOR (c:Control) ON (c.requirement);

// 2. Tenant Isolation Lookups
CREATE INDEX provision_tenant_index IF NOT EXISTS 
FOR (p:Provision) ON (p.tenant_id);

// 3. Temporal Tracking
CREATE INDEX document_created_index IF NOT EXISTS 
FOR (d:Document) ON (d.created_at);
