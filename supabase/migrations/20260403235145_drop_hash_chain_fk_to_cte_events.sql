
-- The canonical persistence path writes to traceability_events first, then hash_chain,
-- then dual-writes to cte_events. The old FK pointed at cte_events which breaks the
-- new write order. Drop it — integrity is enforced by the application layer.
ALTER TABLE fsma.hash_chain DROP CONSTRAINT hash_chain_cte_event_id_fkey;
;
