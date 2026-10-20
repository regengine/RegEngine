-- Columns for app/local_factory.py live LegiScan bills. Idempotent; applied by
-- initdb on a fresh volume and by pipeline.ensure_schema on every run.

ALTER TABLE bill_versions ADD COLUMN IF NOT EXISTS version_stage text;

ALTER TABLE extracted_rules ADD COLUMN IF NOT EXISTS opportunity_score_vs smallint
    CHECK (opportunity_score_vs BETWEEN 0 AND 100);
