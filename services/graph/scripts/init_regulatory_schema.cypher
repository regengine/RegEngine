// ============================================================================
// RegEngine Core Regulatory Schema - Production Ready Integrity
// ============================================================================
// This script establishes the foundational constraints and indexes for the
// Regulatory Knowledge Graph.
//
// NOTE: Document / Provision / Threshold constraints were removed alongside
// deletion of the dead MERGE path in services/graph/app/neo4j_utils.py and
// services/graph/app/consumer.py (2026-05-12). Those labels had 0 nodes in
// prod and were only written by an orphaned consumer that was never wired
// into main.py. DROP statements are included so existing environments shed
// the unused constraints cleanly.
// ============================================================================

// --- DROP DEAD CONSTRAINTS (Document/Provision/Threshold) ---
DROP CONSTRAINT document_id_unique IF EXISTS;
DROP CONSTRAINT document_hash_unique IF EXISTS;

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

// 4. Concept Uniqueness
// Unified terminology Concept mapping.
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS UNIQUE;


// --- INDEXES ---

// 1. Semantic Search & Lookup Performance
CREATE INDEX control_requirement_index IF NOT EXISTS
FOR (c:Control) ON (c.requirement);
