-- Sandbox shareable results: store evaluation results with a short token
-- for shareable URLs. Auto-expire after 30 days. No RLS needed (public table).

CREATE TABLE IF NOT EXISTS sandbox_shares (
    id          TEXT PRIMARY KEY,                        -- 16-char URL-safe token
    csv_text    TEXT NOT NULL,
    result_json JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '30 days',
    ip_hash     TEXT,                                   -- SHA-256 of client IP
    view_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sandbox_shares_expires ON sandbox_shares (expires_at);

-- Cleanup function: delete expired shares
CREATE OR REPLACE FUNCTION cleanup_expired_sandbox_shares()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM sandbox_shares WHERE expires_at < now();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
