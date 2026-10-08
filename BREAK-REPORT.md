# Scheduler break report

Summary: 6 breaks found, 6 fixed and tested, 0 fixed but failing, 0 blocked.

Local tests only. No production URLs, no live Postgres, no SafetyCulture webhook HMAC, no demo-tenant or key-allowlist code.

## High: lost leader still started the job loop

What broke: during the first FDA scrape the heartbeat can decide the advisory lock is gone and call scheduler.shutdown(). APScheduler raises "Scheduler is not running" because start() has not been called. That error was swallowed, the heartbeat thread exited, and the workload still called start(). This process then ran jobs with nobody left watching the lock.

How to reproduce: services/scheduler/tests/test_break_leadership_race.py. A fake engine grants the lock once, then the heartbeat thread always sees it missing. The stand-in initial scrape waits until `_is_leader` is false. On the old code `scheduler.started` was True, and the logs showed `leadership_lost_shutdown_failed` with "Scheduler is not running". A second test cleared the flag inside the first scraper and the old code still ran all three sources.

Root cause: services/scheduler/service.py:1383 (`shutdown` before `start`) and the old `_run_scheduler_workload`, which always continued into `run_initial_scrape` and `scheduler.start()` after the flag was already false. The flag itself is cleared in services/scheduler/app/distributed.py before the callback.

Fix: `_holds_leadership()` reads `_is_leader`. The workload returns before the scrape (service.py:1402) and before `start()` (service.py:1409). `run_initial_scrape` returns at the start of each source (service.py:1323) so later FDA scrapes do not run.

Tests: both leadership break tests pass. Related: test_leader_heartbeat_1142.py and test_leadership_flag.py, included in the 118 passed run below.

## High: one Kafka batch could hide the other's delivery failure

What broke: async delivery failures shared one counter. Two batches can flush the same producer (the scheduler allows overlapping jobs). Whichever batch took the counter first consumed the other batch's failures. The other batch reported success, and service.py can mark those items seen.

How to reproduce: services/scheduler/tests/test_break_kafka_failure_injection.py::test_concurrent_batches_each_see_their_own_delivery_failure. A fake broker waits until both batches have produced, the first flush delivers both rejection callbacks, and the second flush waits until the first batch has taken the counter. On the old code the results were [(0, 2), (1, 0)]. An earlier looser version of this test passed on the old code because both flushes could each see a non-zero count. That version was not kept.

Root cause: services/scheduler/app/kafka_producer.py `_note_delivery_failure` incremented `_delivery_failures`, and `emit_batch` / `emit_fsma_batch` called `take_delivery_failures()` after flush. The errback did not know which batch had sent the message.

Fix: each batch sets a contextvar to its own list before sending (kafka_producer.py:237 and :320). `_send` captures that list and passes it into the errback (kafka_producer.py:389). The errback does not read the contextvar at callback time, because one batch's flush can run the other batch's callback. After flush the batch counts `len(sink) + take_delivery_failures()`, so the older flush mock in test_kafka_delivery_ack_2711.py still counts. Sends outside a batch still use the process counter.

Tests: the concurrent test passes. test_kafka_delivery_ack_2711.py, test_kafka_producer.py, and test_kafka_producer_delivery_handle_2969.py are in the 118 passed run.

## High: a failed high-priority alert was reported as a clean batch

What broke: `emit_batch` ignored the False return from `emit_high_priority_alert`. A critical item whose alert topic rejected the send still came back as zero failures, so the item could be marked seen.

How to reproduce: test_high_priority_alert_send_failure_counts_as_batch_failure in the same file. The fake producer's second `send` raises KafkaError("alerts topic down"). On the old code `failures` was 0, with a `kafka_send_failed` log for topic alerts.

Root cause: services/scheduler/app/kafka_producer.py, the old call that invoked `emit_high_priority_alert` and discarded the bool. The check is now kafka_producer.py:249.

Fix: if the alert send returns False, add one to the batch failure count.

Tests: that test passes in the 118 passed run. A failed alert makes the batch failure count non-zero, so the seen-ack path will not treat the batch as clean. Those items can be sent again on a later pass.

## High: circuit breaker stayed open after the clock stepped backward

What broke: recovery compared `time.time()` to `_opened_at`. If the wall clock moved backward (NTP, or a VM resume), the difference stayed negative and `can_execute()` kept returning false. A monotonic open time of 0.0 would also stick, because the old check treated 0 as missing.

How to reproduce: services/scheduler/tests/test_break_circuit_breaker_clock.py. Open a breaker with a 30 second recovery, step the wall clock back an hour, advance the monotonic clock by 30 seconds. On the old code `can_execute()` stayed false and the state stayed OPEN. The zero-timestamp test also stayed OPEN because recovery still used the wall clock.

Root cause: services/scheduler/app/circuit_breaker.py, old `can_execute` OPEN branch (`if self._opened_at and (time.time() - self._opened_at)`) and `_transition_to_open` storing `time.time()`.

Fix: store `time.monotonic()` (circuit_breaker.py:138) and recover when `_opened_at is not None` and the monotonic delta has elapsed (circuit_breaker.py:81). Last-success and last-failure display times still use the wall clock. Failure counts are still cumulative until the breaker fully closes. That behavior was not changed.

Tests: both clock tests pass. test_circuit_breaker.py is in the 118 passed run.

## High: import-alert parser published non-http links

What broke: `parse_html` ran `urljoin` on every href and stored the result. `javascript:`, `data:`, and `file:` links became item URLs. The alert number was marked seen first, so a later real http(s) link for the same number was dropped.

How to reproduce: test_import_alert_parser_drops_non_http_urls_and_keeps_real_rows. The table has javascript, file, and data rows, a second 16-120 row with an https FDA link, a relative ok.html row, and an absolute accessdata.fda.gov row. On the old code 16-120 was `javascript:alert(1)`.

Root cause: services/scheduler/app/scrapers/fda_import_alerts.py, the old loop that called `seen_alert_numbers.add` before building and checking the URL.

Fix: `urlparse` the joined URL and skip schemes other than http or https (fda_import_alerts.py:209) before marking the number seen (line 216). Relative links and absolute https://www.accessdata.fda.gov links are unchanged. Hosts other than fda.gov are still allowed when the scheme is http or https.

Tests: the break test passes. test_fda_import_alerts_parser_1140.py is in the 118 passed run.

## Medium: unreadable warning-letter RSS skipped the API fallback

What broke: `_scrape_rss` called `ElementTree.fromstring` outside the per-item try. A truncated feed raises ParseError, which is a SyntaxError, not a ValueError. `scrape()` does not catch it, so the openFDA fallback never ran and the error escaped. A feed that defusedxml rejects (entities) raises EntitiesForbidden, which is a ValueError. `scrape()` caught that, marked the scrape failed, and still did not call the API.

How to reproduce: test_truncated_rss_falls_back_to_api and test_rss_with_entities_falls_back_to_api. Fetch is faked. The RSS URL returns a truncated `rss` document, or a DOCTYPE with an external entity. The other URL returns one openFDA result, recall F-0001-2026. On the old code the truncated body raised ParseError ("no element found"), and the entity body returned success False. A first attempt used well-formed `<html>...</html>`, which defusedxml accepted as XML, so that test passed on the old code and was replaced.

Root cause: services/scheduler/app/scrapers/fda_warning_letters.py, `ElementTree.fromstring` at the old unguarded call. `scrape()` only catches HTTP errors, connection errors, timeout, ValueError, and KeyError.

Fix: catch the parse error around `fromstring` only (fda_warning_letters.py:134), log `rss_unreadable_falling_back_to_api`, and return an empty list so `scrape()` uses the API. HTTP errors are still re-raised above that call.

Tests: both fallback tests pass. test_fda_parser_1154.py is in the 118 passed run.

## Test run after the fixes

Command:

~/metacode/fleet/heavy .venv/bin/pytest --no-cov -p no:cacheprovider --tb=line services/scheduler/tests/test_break_leadership_race.py services/scheduler/tests/test_break_circuit_breaker_clock.py services/scheduler/tests/test_break_malformed_scrape.py services/scheduler/tests/test_break_kafka_failure_injection.py services/scheduler/tests/test_circuit_breaker.py services/scheduler/tests/test_leader_heartbeat_1142.py services/scheduler/tests/test_leadership_flag.py services/scheduler/tests/test_kafka_producer.py services/scheduler/tests/test_kafka_producer_delivery_handle_2969.py services/scheduler/tests/test_kafka_delivery_ack_2711.py services/scheduler/tests/test_fda_import_alerts_parser_1140.py services/scheduler/tests/test_fda_parser_1154.py

Result: 118 passed in 1.78s.

Lint: `.venv/bin/ruff check` on the touched scheduler files reported "All checks passed". `ruff format` rewrote five of those files first.

The full repository suite was not run. Nothing was left running.

## Open questions

The gap between the leadership check and `scheduler.start()` is still there. A lock loss in that moment can still call shutdown before start() has begun. Closing it by holding a lock across start() can deadlock the heartbeat thread. Left as is.

https links that are not on an FDA host are still stored. Only non-http schemes are dropped. Say if those off-site links should be dropped too.

The advisory-lock query against `pg_locks` was not executed on Postgres. No failing test pointed at it, so it was not changed.

`app.leadership.is_leader()` builds its own context and the jobs do not call it. `leadership_claim` can yield more than once on standby and production does not use it. Neither was changed.

Cumulative breaker failures (a success in the closed state does not reset the count) were left as they are. The close path already resets the count.
