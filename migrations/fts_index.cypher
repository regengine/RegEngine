-- =============================================================================
-- Phase 29: Full-Text Search Index Migration
-- Run once against the live Neo4j instance.
-- Safe to re-run: the IF NOT EXISTS guard prevents duplicate index creation.
-- =============================================================================

-- Full-text index on Section nodes (title + text body)
CREATE FULLTEXT INDEX sectionText IF NOT EXISTS
FOR (s:Section)
ON EACH [s.title, s.text];

-- Full-text index on Obligation nodes (description)
CREATE FULLTEXT INDEX obligationText IF NOT EXISTS
FOR (o:Obligation)
ON EACH [o.description];

-- Verify indexes were created
SHOW FULLTEXT INDEXES;
