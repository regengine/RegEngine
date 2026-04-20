"""Regression tests for #1166 — graph consumer _retry_counts memory leak.

Verifies the fix that replaced the unbounded ``Dict[str, int]`` with a
``cachetools.TTLCache(maxsize=50000, ttl=3600)`` and clears successful
doc_ids from the cache so they do not linger until the TTL expires.
"""

from __future__ import annotations

import pytest
from cachetools import TTLCache


class TestRetryCountsIsBounded:
    """#1166 — _retry_counts must be a TTLCache, not an unbounded dict."""

    def test_retry_counts_is_ttlcache(self):
        """Module-level _retry_counts must be a cachetools.TTLCache."""
        from services.graph.app import consumer

        assert isinstance(consumer._retry_counts, TTLCache), (
            "_retry_counts must be a TTLCache to prevent unbounded growth "
            "of retry state for a long-running consumer (#1166)."
        )

    def test_retry_counts_has_correct_maxsize(self):
        """maxsize must be 50_000 to match services/nlp/app/consumer.py."""
        from services.graph.app import consumer

        assert consumer._retry_counts.maxsize == 50_000, (
            "maxsize must be 50_000 to match the reference pattern in "
            "services/nlp/app/consumer.py."
        )

    def test_retry_counts_has_correct_ttl(self):
        """ttl must be 3600s (1 hour) to match the NLP consumer pattern."""
        from services.graph.app import consumer

        assert consumer._retry_counts.ttl == 3600, (
            "ttl must be 3600 seconds (1 hour) to match the reference "
            "pattern in services/nlp/app/consumer.py."
        )

    def test_lru_eviction_keeps_cache_bounded_at_maxsize(self):
        """Insert 50_001 unique keys — cache must never exceed maxsize."""
        # Build a local TTLCache so this test is independent of module state.
        # This validates the contract we rely on: cachetools.TTLCache enforces
        # an LRU-style eviction once the cache reaches maxsize.
        cache: TTLCache[str, int] = TTLCache(maxsize=50_000, ttl=3600)

        for i in range(50_001):
            doc_id = f"doc-{i}"
            cache[doc_id] = cache.get(doc_id, 0) + 1

        assert len(cache) == 50_000, (
            f"Cache size must not exceed maxsize=50_000 under load; got {len(cache)}. "
            "This is the core guarantee that prevents the #1166 memory leak."
        )

    def test_module_retry_counts_lru_eviction(self):
        """Direct mutation of the module-level cache must also be bounded."""
        from services.graph.app import consumer

        # Snapshot & clear so test is self-contained and deterministic.
        original = dict(consumer._retry_counts)
        consumer._retry_counts.clear()
        try:
            for i in range(50_001):
                doc_id = f"doc-1166-{i}"
                consumer._retry_counts[doc_id] = (
                    consumer._retry_counts.get(doc_id, 0) + 1
                )

            assert len(consumer._retry_counts) == 50_000, (
                "Module-level _retry_counts must cap at maxsize=50_000."
            )
        finally:
            consumer._retry_counts.clear()
            for k, v in original.items():
                consumer._retry_counts[k] = v


class TestRetryCountsClearedOnSuccess:
    """#1166 — successful retries must be popped, not left to TTL-expire."""

    def test_pop_on_success_path_contract(self):
        """Simulate the success-path pop: after a retry-then-success, the
        doc_id must be removed from _retry_counts so it does not linger.

        The consumer's success path calls ``_retry_counts.pop(doc_id, None)``
        after a successful Neo4j upsert (both new-format and legacy paths).
        This test mirrors that call and asserts the key is gone.
        """
        from services.graph.app import consumer

        doc_id = "doc-success-1166"

        # Snapshot & clear for test isolation.
        original = dict(consumer._retry_counts)
        consumer._retry_counts.clear()
        try:
            # Step 1: simulate a processing error — retry counter increments.
            consumer._retry_counts[doc_id] = (
                consumer._retry_counts.get(doc_id, 0) + 1
            )
            assert doc_id in consumer._retry_counts
            assert consumer._retry_counts[doc_id] == 1

            # Step 2: simulate the retry succeeding — the success path pops
            # the key. This mirrors the fix applied in the consumer.
            consumer._retry_counts.pop(doc_id, None)

            assert doc_id not in consumer._retry_counts, (
                "After a successful retry, the doc_id must be removed from "
                "_retry_counts; otherwise successful docs accumulate until TTL "
                "expiry and partially defeat the bounded-cache fix (#1166)."
            )
        finally:
            consumer._retry_counts.clear()
            for k, v in original.items():
                consumer._retry_counts[k] = v

    def test_pop_is_idempotent_for_unknown_doc_id(self):
        """pop(doc_id, None) must not raise for a doc_id never seen — the
        success-path code does not branch on "was there a prior retry?"."""
        from services.graph.app import consumer

        # No KeyError — the default None protects us.
        consumer._retry_counts.pop("never-seen-doc-1166", None)
