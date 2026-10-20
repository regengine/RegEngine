-- pgvector copycat detection for app/local_factory.py. Idempotent; applied by
-- initdb on a fresh volume and by pipeline.ensure_schema on every run, so an
-- already initialized volume gets it on the next live or dry run. Needs the
-- pgvector/pgvector image from docker-compose.yml.

CREATE EXTENSION IF NOT EXISTS vector;

-- No fixed dimension: different embedding models can share the column, and the
-- copycat query only compares rows whose vector_dims match.
ALTER TABLE bill_versions ADD COLUMN IF NOT EXISTS full_text_embedding vector;
