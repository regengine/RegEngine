-- V053: Add 'growing' to the event_type CHECK constraint on traceability_events.
-- FSMA 204 §1.1310 defines Growing as a Critical Tracking Event for raw
-- agricultural commodities prior to harvesting.

ALTER TABLE fsma.traceability_events
    DROP CONSTRAINT IF EXISTS traceability_events_event_type_check;

ALTER TABLE fsma.traceability_events
    ADD CONSTRAINT traceability_events_event_type_check
    CHECK (event_type IN (
        'growing', 'harvesting', 'cooling', 'initial_packing',
        'first_land_based_receiving',
        'shipping', 'receiving', 'transformation'
    ));
