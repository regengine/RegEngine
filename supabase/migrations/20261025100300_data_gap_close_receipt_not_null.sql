-- DeepSeek FAIL on #3600: with closing_record_hash NULL the regex test is
-- NULL, so the CHECK passed and a closed gap could lack a receipt.
-- Prod had 0 rows in data_gap_events when this was written (2026-10-25).
ALTER TABLE public.data_gap_events
  DROP CONSTRAINT IF EXISTS data_gap_events_close_receipt_check;
ALTER TABLE public.data_gap_events
  ADD CONSTRAINT data_gap_events_close_receipt_check CHECK (
    (closed_at IS NULL AND closing_record_id IS NULL AND closing_record_hash IS NULL)
    OR (
      closed_at IS NOT NULL
      AND closed_at >= opened_at
      AND closing_record_hash IS NOT NULL
      AND closing_record_hash ~ '^[0-9a-f]{64}$'
    )
  );
