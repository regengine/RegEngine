"""Regression tests for the query-path extraction-dedup audit finding (low).

Finding: ``services/nlp/app/consumer/__init__.py`` extracted the same
per-record fields (doc_hash / norm_path / inline_text / provenance) twice,
once before tenant resolution and once after, reading the same ``evt``
dict both times. The second copy was redundant dead weight with its own
stale comment, and the tenant-resolution success metric beside it used a
misleading label: ``outcome="from_header"`` whenever a header tenant id
was present, implying the tenant came from the header. Tenant resolution
is always authoritative from the signed payload body (RE-SEC-001); the
Kafka header is advisory only.

Locked-in behavior after the fix:

1. The ``evt.get("document_hash")`` extraction appears exactly once.
2. The success metric uses ``resolved_with_header`` /
   ``resolved_payload_only`` labels and never ``from_header``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

_CONSUMER_SRC = _repo_root / "services" / "nlp" / "app" / "consumer" / "__init__.py"


def _source() -> str:
    return _CONSUMER_SRC.read_text(encoding="utf-8")


def test_field_extraction_block_is_not_duplicated():
    """The doc_hash/norm_path/inline_text extraction must exist once.

    The old code read the same ``evt`` dict fields in two back-to-back
    blocks (pre-tenant and post-tenant). The post-tenant copy could never
    observe different values, so it was removed.
    """
    src = _source()
    assert src.count('evt.get("document_hash")') == 1
    assert src.count('evt.get("normalized_s3_path")') == 1
    assert src.count('evt.get("text_clean")') == 1


def test_tenant_resolution_metric_label_is_not_misleading():
    """The success metric must not claim the tenant came from the header."""
    src = _source()
    assert 'outcome="from_header"' not in src
    assert "resolved_with_header" in src
    assert "resolved_payload_only" in src
