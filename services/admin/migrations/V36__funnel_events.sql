-- V36: Tenant conversion funnel event tracking

CREATE TABLE IF NOT EXISTS funnel_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_name TEXT NOT NULL CHECK (
        event_name IN (
            'signup_completed',
            'first_ingest',
            'first_scan',
            'first_nlp_query',
            'checkout_started',
            'payment_completed'
        )
    ),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, event_name)
);

CREATE INDEX IF NOT EXISTS idx_funnel_events_event_name ON funnel_events (event_name);
CREATE INDEX IF NOT EXISTS idx_funnel_events_created_at ON funnel_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_funnel_events_tenant_created ON funnel_events (tenant_id, created_at DESC);
