-- COALESCE and a nil-UUID literal that have nothing to do with a tenant
-- predicate must NOT trip the guard (this shape appears in real audit
-- triggers and unique indexes, e.g. V066 and V080's uq_ index).
CREATE UNIQUE INDEX uq_demo_idem ON fsma.demo_events (
    tenant_id,
    COALESCE(event_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(rule_id, ''),
    created_at
);

CREATE OR REPLACE FUNCTION fsma.demo_audit() RETURNS TRIGGER AS $$
BEGIN
    RAISE NOTICE '% % %', TG_OP, current_user, COALESCE(NEW.id::text, OLD.id::text);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
