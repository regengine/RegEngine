"""Empty-event rejection for the canonical EPCIS normalizer.

Lot precedence, input quantity lineage, and eventTime refusal need a real
EPCIS event. An empty dict fails earlier, on an unmapped bizStep.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared.canonical_event import normalize_epcis_event


def test_empty_event_is_rejected():
    with pytest.raises(ValueError):
        normalize_epcis_event({}, str(uuid4()))
