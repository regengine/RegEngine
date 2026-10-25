-- Migration A: move extensions out of the public schema (advisor lint extension_in_public, 3).
-- pg_trgm and hypopg are relocated with ALTER EXTENSION ... SET SCHEMA.
-- ALTER EXTENSION has no IF EXISTS form, so those two statements are unguarded.
-- index_advisor does not support SET SCHEMA, so it is dropped and recreated in extensions
-- (it depends on hypopg, which is moved first).
-- Note: SQL calling pg_trgm functions/operators unqualified (similarity(), %, word_similarity())
-- needs `extensions` on search_path after this runs.
-- Generated 2026-10-16 from regengine-fix-plan-2026-10-15.md (S2). Not applied.

ALTER EXTENSION pg_trgm SET SCHEMA extensions;
ALTER EXTENSION hypopg SET SCHEMA extensions;

DROP EXTENSION IF EXISTS index_advisor;
CREATE EXTENSION IF NOT EXISTS index_advisor WITH SCHEMA extensions;
;
