"""Topic names, producer identity, and tuning constants for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

# Producer service identity used when this consumer re-emits events to
# downstream topics (graph.update, nlp.needs_review, nlp.extracted).
# Must match the value the downstream consumer expects in its
# KAFKA_ALLOWED_PRODUCERS_<TOPIC> env var (#1078).
NLP_PRODUCER_SERVICE = "nlp-service"

# Topic names for routing
TOPIC_GRAPH_UPDATE = "graph.update"
TOPIC_NEEDS_REVIEW = "nlp.needs_review"
TOPIC_DLQ = "nlp.extracted.dlq"
TOPIC_FSMA_DLQ = "fsma.dead_letter"

# Max retries before sending to DLQ
MAX_RETRIES = 3

# Heuristic confidence cap for the legacy regex path (#1202).
# The regex pipeline has no calibrated model — every confidence score is an
# invented number. Cap it below the auto-approval gate so nothing from this path
# can bypass HITL. Only the FSMA extractor (calibrated from KDE completeness)
# may exceed this ceiling.
_LEGACY_HEURISTIC_CONFIDENCE_CAP = 0.60

# Confidence cap for generative-LLM extractions (#2947).
# The number an LLM reports about its own output is not a calibrated
# probability, and the document it read is supplier-controlled. Capping below
# the medium routing threshold means a generative extraction can only ever land
# in HITL: it can never be the key that unlocks the auto-approve path to
# graph.update. Raising this above the medium threshold re-opens exactly that.
_LLM_EXTRACTION_CONFIDENCE_CAP = 0.60
