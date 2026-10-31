-- alembic-revision: b005ddbf1dba
-- rendered-from: alembic/versions/20261024_b005ddbf1dba_v136_supplier_agreed_sending_hours.py (upgrade)
-- Agreed sending time per supplier facility.
--
-- agreed_sending_hours is how many hours after a CTE's event time the
-- supplier has agreed to send the record. The supplier data quality view
-- counts a record as late when it is received more than this many hours after
-- its event time. This is our own measure, not an FDA rule. NULL means no
-- agreement is recorded, and the late measure shows not enough data.
--
-- No backfill. Additive and idempotent: the inline CHECK is only created
-- together with the column, so a re-run is a no-op.

alter table public.supplier_facilities
    add column if not exists agreed_sending_hours integer null
        constraint supplier_facilities_agreed_sending_hours_check
            check (agreed_sending_hours > 0);

-- Downgrade (run by hand only; alembic v136 b005ddbf1dba does the same):
--
-- alter table public.supplier_facilities
--     drop constraint if exists supplier_facilities_agreed_sending_hours_check;
-- alter table public.supplier_facilities
--     drop column if exists agreed_sending_hours;
