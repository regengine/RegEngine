"""CSV header -> canonical FSMA 204 field suggestions, answered by Jev.

This is the one place that defines the questions RegEngine asks Jev about a
CSV upload and the policy for what code may do with the answers. Keep the
vocabulary, the wording and the thresholds here so a reviewer can read the
whole decision in one file (see ``docs/architecture/decisions/ADR-005``).

How it works
------------
1. The CSV parser (``services/ingestion/app/csv_templates.py``) recognises a
   fixed set of column names. Columns outside that set pass through as
   opaque KDEs, so a supplier file with ``Lot #`` or ``Ship Dt`` silently
   misses required fields.
2. For each unrecognised column, one ``Choice`` question asks Jev which
   canonical field the column represents, or ``no_match``. All questions for
   an upload go in a single request and are evaluated in parallel. When the
   uploader declares one CTE for the whole file (the route's ``cte_type``
   form field), the state carries it as ``file_cte_type`` so a header such as
   ``Ship Dt`` is read knowing the file records shipping events.
3. Every answer is banded by confidence (:mod:`shared.jev.routing`) and
   recorded as an advisory ``field_mapping_suggestion`` agent artifact
   (:mod:`shared.agent_artifacts`), anchored to the upload's SHA-256 and its
   ingestion run, with the model, request id, probabilities and thresholds in
   the rationale. Artifacts surface in the Agent Reviews queue.
4. A mapping is *applied* to the rows only when all of the following hold:
   the operator enabled ``REGENGINE_JEV_APPLY_HEADER_MAPPINGS``, the answer
   is in the ``AUTO_APPLY`` band, the confidence clears the agent-artifact
   human-review threshold, the target field is not already present in the
   file, and no other column competes for the same target. Applying copies
   the value under the canonical key; the source column is left untouched so
   nothing is lost from the evidence trail.

What leaves the process: the CSV header row and, only when
``REGENGINE_JEV_HEADER_SAMPLE_VALUES`` is set, up to that many PII-redacted
sample values per unrecognised column. Never whole rows: a header row that
spans lines, contains a line break or has a header over
:data:`MAX_HEADER_CHARS` characters is refused (``malformed_header``) and
nothing is sent.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog
from shared.agent_artifacts import (
    AGENT_ARTIFACT_VERSION,
    HUMAN_REVIEW_CONFIDENCE_THRESHOLD,
    AgentArtifact,
    AgentArtifactContext,
    FieldMappingSuggestionPayload,
)
from shared.pii import redact_pii

from .client import JevDecider, JevEvidence, JevUnavailable, get_jev_decider
from .routing import ConfidenceBand, ConfidenceThresholds, band_for_confidence

logger = structlog.get_logger("jev.header_mapping")

# Recorded with every answer and artifact. Bump it whenever the question text,
# the vocabulary or the meaning of a state key changes, so the evidence says
# exactly what was asked. v2: the task text explains ``file_cte_type``.
QUESTIONS_VERSION = "csv-header-mapping.v2"
AGENT_NAME = "jev-csv-header-mapper"
PURPOSE = "csv_header_mapping"
NO_MATCH = "no_match"
MAX_COLUMNS_PER_UPLOAD = 48
MAX_SAMPLE_VALUE_CHARS = 64
# Longest header, after stripping, that can be a real column name. The
# longest name RegEngine itself uses is 25 characters
# (``immediate_previous_source``) and the longest vocabulary example is 21
# (``Ingredient Quantities``); descriptive ERP export headers run to 40-60.
# 128 leaves that 2x headroom. Anything longer is almost certainly row data
# swallowed into the header (an unterminated quote), so it is never sent.
MAX_HEADER_CHARS = 128
MALFORMED_HEADER = "malformed_header"

# Canonical vocabulary. Keys are the exact column names the CSV parser and
# the FSMA validators consume. Descriptions follow the vendor guidance for
# confusable options: what the field is, what it is not, example headers.
CANONICAL_FIELDS: dict[str, dict[str, Any]] = {
    "traceability_lot_code": {
        "what": "The FSMA 204 traceability lot code (TLC) that identifies this lot of food.",
        "not_for": "Input or ingredient lot codes of a transformation, purchase orders, invoice numbers.",
        "examples": ["TLC", "Lot", "Lot #", "Lot Code", "Batch", "Batch No"],
    },
    "product_description": {
        "what": "Human-readable name or description of the food product.",
        "not_for": "Product codes with no description, brand-only columns.",
        "examples": ["Product", "Item", "Commodity", "Description", "Item Description"],
    },
    "quantity": {
        "what": "Numeric quantity of the lot in the event.",
        "not_for": "The unit name, prices, weights of packaging, input quantities of a transformation.",
        "examples": ["Qty", "Quantity", "Cases", "Count", "Amount", "Pallets Shipped"],
    },
    "unit_of_measure": {
        "what": "Unit that the quantity is expressed in.",
        "not_for": "The numeric quantity itself.",
        "examples": ["UOM", "Unit", "Units", "Pack Type", "Unit of Measure"],
    },
    "location_name": {
        "what": "Name of the facility or place where this event happened.",
        "not_for": "Ship-to or ship-from locations of a shipment, receiving sites, GLN numbers.",
        "examples": ["Facility", "Site", "Location", "Farm", "Plant", "Field Location"],
    },
    "location_gln": {
        "what": "GS1 Global Location Number (13 digits) of the event location.",
        "not_for": "Location names, GTINs, other identifiers.",
        "examples": ["GLN", "Location GLN", "Site GLN"],
    },
    "event_date": {
        "what": "Calendar date on which the event occurred, when the column does not say which event.",
        "not_for": "Times of day, expiry or best-before dates, dates of a specifically named event.",
        "examples": ["Date", "Event Date", "Txn Date", "Activity Date"],
    },
    "event_time": {
        "what": "Time of day at which the event occurred.",
        "not_for": "Dates, durations.",
        "examples": ["Time", "Event Time", "Timestamp Time"],
    },
    "harvest_date": {
        "what": "Date the food was harvested.",
        "not_for": "Cooling, packing, shipping or receiving dates.",
        "examples": ["Harvest Date", "Harvested On", "Pick Date"],
    },
    "cooling_date": {
        "what": "Date the food was cooled.",
        "not_for": "Other dated events.",
        "examples": ["Cooling Date", "Cooled On", "Chill Date"],
    },
    "packing_date": {
        "what": "Date the food was initially packed.",
        "not_for": "Other dated events.",
        "examples": ["Pack Date", "Packing Date", "Packed On"],
    },
    "ship_date": {
        "what": "Date the food was shipped.",
        "not_for": "Receiving dates, order dates, delivery due dates.",
        "examples": ["Ship Date", "Ship Dt", "Shipped On", "Dispatch Date"],
    },
    "receive_date": {
        "what": "Date the food was received.",
        "not_for": "Shipping dates, order dates.",
        "examples": ["Receive Date", "Received On", "Recv Date", "Delivery Date"],
    },
    "transformation_date": {
        "what": "Date the food was transformed (processed, combined, repacked).",
        "not_for": "Other dated events.",
        "examples": ["Transformation Date", "Process Date", "Production Date"],
    },
    "landing_date": {
        "what": "Date seafood was landed at the first land-based receiver.",
        "not_for": "Other dated events.",
        "examples": ["Landing Date", "Landed On", "Offload Date"],
    },
    "ship_from_location": {
        "what": "Location the shipment was sent from.",
        "not_for": "Destination locations, the event location of non-shipping events.",
        "examples": ["Ship From", "Origin", "Shipped From", "From Location"],
    },
    "ship_to_location": {
        "what": "Location the shipment was sent to.",
        "not_for": "Origin locations.",
        "examples": ["Ship To", "Destination", "Consignee", "Deliver To"],
    },
    "ship_from_gln": {
        "what": "GS1 GLN of the ship-from location.",
        "not_for": "Names, ship-to GLNs.",
        "examples": ["Ship From GLN", "Origin GLN"],
    },
    "ship_to_gln": {
        "what": "GS1 GLN of the ship-to location.",
        "not_for": "Names, ship-from GLNs.",
        "examples": ["Ship To GLN", "Destination GLN"],
    },
    "receiving_location": {
        "what": "Location where the food was received.",
        "not_for": "Where it was shipped from.",
        "examples": ["Receiving Site", "Received At", "Delivered To", "Receiving Location"],
    },
    "receiving_gln": {
        "what": "GS1 GLN of the receiving location.",
        "not_for": "Names.",
        "examples": ["Receiving GLN"],
    },
    "reference_document": {
        "what": "Reference document type and number for the event (bill of lading, invoice, purchase order, harvest record).",
        "not_for": "Lot codes, internal row ids.",
        "examples": ["BOL", "Bill of Lading", "Invoice #", "PO Number", "Ref Doc", "Reference"],
    },
    "tlc_source_reference": {
        "what": "The traceability lot code source or its reference: where the TLC was assigned.",
        "not_for": "The TLC itself, the shipper.",
        "examples": ["TLC Source", "TLC Source Reference", "Lot Assigned At"],
    },
    "immediate_previous_source": {
        "what": "The immediate previous source of the food for a receiving event (who it was received from).",
        "not_for": "Carriers, ship-to parties.",
        "examples": ["Supplier", "Shipper", "Received From", "Vendor", "Previous Source"],
    },
    "harvester_business_name": {
        "what": "Business name of the harvester, recorded at initial packing.",
        "not_for": "Packer names, carriers.",
        "examples": ["Harvester", "Harvester Name", "Grower"],
    },
    "harvester_business_phone": {
        "what": "Phone number of the harvester business.",
        "not_for": "Other phone numbers.",
        "examples": ["Harvester Phone", "Grower Phone"],
    },
    "input_lot_codes": {
        "what": "Lot codes of the inputs consumed by a transformation, possibly comma separated.",
        "not_for": "The output traceability lot code.",
        "examples": ["Input Lots", "Ingredient Lots", "Source TLCs", "Input TLC"],
    },
    "input_quantities": {
        "what": "Quantities of each transformation input, aligned with the input lot codes.",
        "not_for": "Output quantity.",
        "examples": ["Input Qty", "Ingredient Quantities"],
    },
    "input_units_of_measure": {
        "what": "Units for each transformation input quantity.",
        "not_for": "Output unit.",
        "examples": ["Input UOM", "Ingredient Units"],
    },
    "cte_type": {
        "what": "The critical tracking event type of the row (harvesting, cooling, initial packing, shipping, receiving, transformation, first land-based receiving).",
        "not_for": "Product types, document types.",
        "examples": ["Event Type", "CTE", "Activity", "Transaction Type"],
    },
    "carrier": {
        "what": "Transport carrier or trucking company that moved the shipment.",
        "not_for": "Suppliers, ship-to parties.",
        "examples": ["Carrier", "Trucking Co", "Transport", "Hauler"],
    },
    NO_MATCH: {
        "what": "The column is none of the fields above: internal ids, notes, prices, temperatures, weights of packaging, or anything RegEngine does not model.",
        "examples": ["Row ID", "Notes", "Price", "Temp C", "Pallet Weight", "Approved By"],
    },
}

CANONICAL_FIELD_NAMES: frozenset[str] = frozenset(name for name in CANONICAL_FIELDS if name != NO_MATCH)


def normalize_csv_header(header: str | None) -> str:
    """Normalise a header exactly as the CSV parser does before it looks up columns."""
    return (header or "").strip().lower().replace(" ", "_")


def malformed_header_reason(headers: Iterable[str | None]) -> str | None:
    """Why this cannot be a real header row, or ``None`` when it can.

    An unterminated quote makes the CSV reader take the rest of the file as
    one header, so whole rows would leave the process as a "column name". A
    header with a line break, or longer than :data:`MAX_HEADER_CHARS`, is
    refused. The reason names the problem, never the header's content.
    """
    for header in headers:
        text = (header or "").strip()
        if "\r" in text or "\n" in text:
            return "a header contains a line break"
        if len(text) > MAX_HEADER_CHARS:
            return f"a header is {len(text)} characters long (limit {MAX_HEADER_CHARS})"
    return None


def unrecognized_headers(headers: Iterable[str | None], recognized: Collection[str]) -> list[str]:
    """Return the original headers whose normalised form the parser does not recognise.

    Blank headers and duplicates (after normalisation) are dropped: the
    parser cannot address them, so there is nothing to map.
    """
    seen: set[str] = set()
    unknown: list[str] = []
    for header in headers:
        key = normalize_csv_header(header)
        if not key or key in recognized or key in seen:
            continue
        seen.add(key)
        unknown.append((header or "").strip())
    return unknown


def build_state(
    all_headers: Sequence[str],
    columns: Sequence[str],
    samples: Mapping[str, Sequence[str]] | None,
    *,
    cte_type: str | None = None,
) -> dict[str, Any]:
    """Assemble the state object: the whole header row for context plus the columns to map.

    ``cte_type`` is the canonical CTE (for example ``shipping``) the uploader
    declared for every row of the file. It is added as ``file_cte_type`` only
    when given, so the state for a file without one is exactly what it was
    before the key existed.
    """
    to_map: list[dict[str, Any]] = []
    for index, header in enumerate(columns):
        entry: dict[str, Any] = {"index": index, "header": header}
        values = list(samples.get(header, ())) if samples else []
        if values:
            entry["sample_values"] = values
        to_map.append(entry)
    state: dict[str, Any] = {
        "csv_headers": [(header or "").strip() for header in all_headers],
        "columns_to_map": to_map,
    }
    if cte_type:
        state["file_cte_type"] = cte_type
    return state


def build_questions(columns: Sequence[str]) -> dict[str, dict[str, Any]]:
    """One Choice question per column, keyed ``col_<index>``.

    Questions are plain dictionaries (the SDK accepts them) so this module
    stays importable without constructing SDK objects at import time.
    """
    questions: dict[str, dict[str, Any]] = {}
    for index, header in enumerate(columns):
        questions[f"col_{index}"] = {
            "type": "choice",
            "instructions": {
                "task": (
                    "Decide which canonical FSMA 204 traceability field the CSV column described in "
                    "`column` represents. Use `csv_headers` in the state for context about the file. "
                    "When the state has `file_cte_type`, it names the FSMA 204 critical tracking event "
                    "that every row in the file records."
                ),
                "column": {"path": f"columns_to_map[{index}]", "header": header},
                "guidance": (
                    f"Choose the field whose meaning matches the column header. Choose {NO_MATCH} when "
                    "the column is not one of the listed fields. Do not guess from position alone."
                ),
            },
            "criteria": CANONICAL_FIELDS,
        }
    return questions


@dataclass(frozen=True)
class HeaderMappingSuggestion:
    """Jev's read on one unrecognised column and what code did with it."""

    source_header: str
    source_key: str
    canonical_field: Optional[str]
    confidence: float
    band: ConfidenceBand
    probabilities: dict[str, float] = field(default_factory=dict)
    applied: bool = False
    blocked_reason: Optional[str] = None
    shadowed_columns: tuple[str, ...] = ()
    sample_value: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_header": self.source_header,
            "source_key": self.source_key,
            "canonical_field": self.canonical_field,
            "confidence": self.confidence,
            "band": self.band.value,
            "probabilities": dict(self.probabilities),
            "applied": self.applied,
            "blocked_reason": self.blocked_reason,
            "shadowed_columns": list(self.shadowed_columns),
        }


@dataclass(frozen=True)
class HeaderMappingResult:
    """All suggestions for one upload plus the evidence for the Jev call."""

    status: str
    suggestions: tuple[HeaderMappingSuggestion, ...] = ()
    evidence: Optional[JevEvidence] = None
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    apply_enabled: bool = False
    truncated_columns: int = 0
    # What Jev was told about the file's CTE: the ``file_cte_type`` put in the
    # request state (``None`` when absent or when no request was built), and,
    # when the uploader declared a CTE that was withheld, why. The route sets
    # the reason (``_suggest_header_mappings_for_upload``); both reach the
    # artifact rationale so the evidence records what was asked.
    file_cte_type: Optional[str] = None
    file_cte_type_dropped: Optional[str] = None

    @property
    def applied_mapping(self) -> dict[str, str]:
        """``source_key -> canonical_field`` for the suggestions the parser must apply."""
        return {s.source_key: s.canonical_field for s in self.suggestions if s.applied and s.canonical_field}

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _top_probabilities(probabilities: Mapping[str, float], limit: int = 3) -> dict[str, float]:
    ordered = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))
    return {label: round(float(p), 4) for label, p in ordered[:limit]}


def outranked_columns(canonical_field: str, precedence: Sequence[Sequence[str]]) -> tuple[str, ...]:
    """Columns the parser consults only after ``canonical_field``.

    ``precedence`` lists, per field, the columns the parser tries in order
    (the first non-empty one wins). A value copied under ``canonical_field``
    would outrank every later column in the same chain, so a mapping onto it
    is refused when the file already carries one of them: applying it would
    silently replace a value the uploader provided.
    """
    outranked: list[str] = []
    for chain in precedence:
        keys = list(chain)
        if canonical_field not in keys:
            continue
        for key in keys[keys.index(canonical_field) + 1 :]:
            if key != canonical_field and key not in outranked:
                outranked.append(key)
    return tuple(outranked)


def _decide(
    columns: Sequence[str],
    answers: Mapping[str, Any],
    *,
    present_keys: Collection[str],
    thresholds: ConfidenceThresholds,
    apply_enabled: bool,
    samples: Mapping[str, Sequence[str]] | None,
    precedence: Sequence[Sequence[str]] = (),
) -> list[HeaderMappingSuggestion]:
    """Turn Choice answers into suggestions and apply the policy deterministically."""
    provisional: list[dict[str, Any]] = []
    for index, header in enumerate(columns):
        answer = answers.get(f"col_{index}")
        if answer is None:
            continue
        choice = answer.choice if answer.choice in CANONICAL_FIELDS else NO_MATCH
        canonical = None if choice == NO_MATCH else choice
        confidence = float(answer.confidence)
        band = band_for_confidence(confidence, thresholds)
        provisional.append(
            {
                "header": header,
                "key": normalize_csv_header(header),
                "canonical": canonical,
                "confidence": confidence,
                "band": band,
                "probabilities": _top_probabilities(answer.probabilities),
            }
        )

    candidates = Counter(
        item["canonical"] for item in provisional if item["canonical"] and item["band"] is ConfidenceBand.AUTO_APPLY
    )

    suggestions: list[HeaderMappingSuggestion] = []
    for item in provisional:
        canonical = item["canonical"]
        shadowed: tuple[str, ...] = ()
        if canonical is not None:
            shadowed = tuple(c for c in outranked_columns(canonical, precedence) if c in present_keys)
        blocked: Optional[str] = None
        if canonical is None:
            blocked = "no_match"
        elif item["band"] is not ConfidenceBand.AUTO_APPLY:
            blocked = "below_auto_apply_threshold"
        elif item["confidence"] < HUMAN_REVIEW_CONFIDENCE_THRESHOLD:
            blocked = "below_human_review_threshold"
        elif not apply_enabled:
            blocked = "apply_disabled"
        elif canonical in present_keys:
            blocked = "target_present"
        elif shadowed:
            blocked = "shadows_existing_column"
        elif candidates[canonical] > 1:
            blocked = "conflict"
        sample = None
        if samples:
            values = list(samples.get(item["header"], ()))
            sample = values[0] if values else None
        suggestions.append(
            HeaderMappingSuggestion(
                source_header=item["header"],
                source_key=item["key"],
                canonical_field=canonical,
                confidence=item["confidence"],
                band=item["band"],
                probabilities=item["probabilities"],
                applied=blocked is None,
                blocked_reason=blocked,
                shadowed_columns=shadowed,
                sample_value=sample,
            )
        )
    return suggestions


def collect_sample_values(
    rows: Iterable[Mapping[str, str | None]],
    columns: Sequence[str],
    limit: int,
    *,
    max_rows: int = 50,
) -> dict[str, list[str]]:
    """Up to ``limit`` distinct, PII-redacted, truncated values per column from the first rows."""
    if limit <= 0 or not columns:
        return {}
    wanted = set(columns)
    collected: dict[str, list[str]] = {header: [] for header in columns}
    for row_index, row in enumerate(rows):
        if row_index >= max_rows:
            break
        for raw_header, raw_value in row.items():
            header = (raw_header or "").strip()
            if header not in wanted or raw_value is None:
                continue
            value = redact_pii(str(raw_value).strip())[:MAX_SAMPLE_VALUE_CHARS]
            bucket = collected[header]
            if value and value not in bucket and len(bucket) < limit:
                bucket.append(value)
        if all(len(bucket) >= limit for bucket in collected.values()):
            break
    return {header: values for header, values in collected.items() if values}


def suggest_header_mappings(
    all_headers: Sequence[str | None],
    *,
    recognized: Collection[str],
    samples: Mapping[str, Sequence[str]] | None = None,
    decider: JevDecider | None = None,
    precedence: Sequence[Sequence[str]] = (),
    cte_type: str | None = None,
) -> HeaderMappingResult:
    """Ask Jev about every unrecognised header. Never raises.

    ``recognized`` is the parser's set of normalised column names.
    ``cte_type`` is the canonical CTE declared for the whole file, or
    ``None`` for a mixed-type or undeclared file (see :func:`build_state`).
    The caller must only pass it when no row can contradict it; the route
    enforces that in ``_file_cte_type_for_jev``.
    ``precedence`` lists the parser's fallback chains (see
    :func:`outranked_columns`) so a mapping is never applied where it would
    outrank a column the file already carries. The decider's settings supply
    thresholds and the apply switch, so the policy is configured in one place.
    """
    decider = decider if decider is not None else get_jev_decider()
    settings = decider.settings
    thresholds = settings.thresholds
    apply_enabled = settings.apply_header_mappings

    if not decider.enabled:
        return HeaderMappingResult(status="disabled", thresholds=thresholds, apply_enabled=apply_enabled)

    # Defence in depth for any caller: the CSV route also refuses a header
    # row that spans lines before it gets here (``_csv_headers_and_samples``).
    if malformed_header_reason(all_headers):
        return HeaderMappingResult(status=MALFORMED_HEADER, thresholds=thresholds, apply_enabled=apply_enabled)

    columns = unrecognized_headers(all_headers, recognized)
    if not columns:
        return HeaderMappingResult(status="no_unrecognized_headers", thresholds=thresholds, apply_enabled=apply_enabled)

    truncated = max(0, len(columns) - MAX_COLUMNS_PER_UPLOAD)
    columns = columns[:MAX_COLUMNS_PER_UPLOAD]
    present_keys = {normalize_csv_header(header) for header in all_headers}
    file_cte_type = cte_type or None

    try:
        answers = decider.ask(
            build_state(list(all_headers), columns, samples, cte_type=file_cte_type),  # type: ignore[arg-type]
            build_questions(columns),
            purpose=PURPOSE,
            questions_version=QUESTIONS_VERSION,
        )
    except JevUnavailable as exc:
        return HeaderMappingResult(
            status=f"unavailable:{exc.reason}",
            thresholds=thresholds,
            apply_enabled=apply_enabled,
            truncated_columns=truncated,
            file_cte_type=file_cte_type,
        )
    except Exception:  # noqa: BLE001 - the upload must not fail because a suggestion did.
        logger.exception("jev.header_mapping.error", column_count=len(columns))
        return HeaderMappingResult(
            status="error",
            thresholds=thresholds,
            apply_enabled=apply_enabled,
            truncated_columns=truncated,
            file_cte_type=file_cte_type,
        )

    suggestions = _decide(
        columns,
        answers.choices,
        present_keys=present_keys,
        thresholds=thresholds,
        apply_enabled=apply_enabled,
        samples=samples,
        precedence=precedence,
    )
    logger.info(
        "jev.header_mapping.suggested",
        column_count=len(columns),
        applied=sum(1 for s in suggestions if s.applied),
        review=sum(1 for s in suggestions if s.band is ConfidenceBand.REVIEW),
        rejected=sum(1 for s in suggestions if s.band is ConfidenceBand.REJECT),
        no_match=sum(1 for s in suggestions if s.canonical_field is None),
        truncated_columns=truncated,
        request_id=answers.evidence.request_id,
    )
    return HeaderMappingResult(
        status="ok",
        suggestions=tuple(suggestions),
        evidence=answers.evidence,
        thresholds=thresholds,
        apply_enabled=apply_enabled,
        truncated_columns=truncated,
        file_cte_type=file_cte_type,
    )


def _blocked_detail(suggestion: HeaderMappingSuggestion) -> str:
    if not suggestion.shadowed_columns:
        return ""
    columns = ", ".join(suggestion.shadowed_columns)
    return f"; the file already carries {columns}, which the parser reads only after {suggestion.canonical_field}"


def _file_cte_note(result: HeaderMappingResult) -> str:
    """What the request state said about the file's CTE, for the artifact rationale.

    The artifact and payload contracts are closed (``extra="forbid"``, a
    checked-in JSON schema, and the payload is hashed into the run ledger),
    so this travels in the free-text rationale next to the question-set
    version instead of as a new field.
    """
    if result.file_cte_type:
        return f"State file_cte_type: {result.file_cte_type}."
    if result.file_cte_type_dropped:
        return f"State file_cte_type: none (declared CTE withheld: {result.file_cte_type_dropped})."
    return "State file_cte_type: none (no CTE declared for the file)."


def _declared_cte_precedence_note(result: HeaderMappingResult) -> str | None:
    """How an applied ``cte_type`` mapping relates to a CTE the uploader declared.

    The parser reads a row's own CTE first and falls back to the declared one
    (``_detect_row_cte_type``), so the mapped column wins wherever it holds a
    known CTE. ``None`` when no CTE was declared.
    """
    if result.file_cte_type:
        declared = f"The declared file CTE {result.file_cte_type}"
    elif result.file_cte_type_dropped:
        declared = "The declared file CTE"
    else:
        return None
    return (
        f"{declared} remains the fallback for rows where this column is blank or not a known CTE; "
        "per-row values from this column override it."
    )


def _rationale(suggestion: HeaderMappingSuggestion, result: HeaderMappingResult) -> str:
    evidence = result.evidence
    parts = [
        f"TypeSafe Jev Choice question ({QUESTIONS_VERSION}) over the canonical FSMA 204 field vocabulary.",
        _file_cte_note(result),
        f"Top probabilities: {suggestion.probabilities}.",
        f"Confidence {suggestion.confidence:.3f} falls in band '{suggestion.band.value}' "
        f"(auto_apply >= {result.thresholds.auto_apply}, review >= {result.thresholds.review}).",
        "Applied to the upload's rows by deterministic code."
        if suggestion.applied
        else f"Not applied to rows (reason: {suggestion.blocked_reason}{_blocked_detail(suggestion)}).",
    ]
    if suggestion.applied and suggestion.canonical_field == "cte_type":
        declared = _declared_cte_precedence_note(result)
        if declared:
            parts.append(declared)
    if evidence is not None:
        parts.append(
            f"Model {evidence.model}, request {evidence.request_id or 'n/a'}, latency {evidence.latency_ms} ms."
        )
    return " ".join(parts)


def build_field_mapping_artifacts(
    result: HeaderMappingResult,
    *,
    tenant_id: str | UUID,
    source_hash: str,
    ingestion_run_id: str | UUID | None = None,
    now: datetime | None = None,
) -> list[AgentArtifact]:
    """Advisory ``field_mapping_suggestion`` artifacts for every actionable suggestion.

    ``no_match`` and ``REJECT``-band answers produce no artifact: there is
    nothing for a reviewer to accept. Anything applied is recorded with
    ``requires_human_review=False`` (its confidence cleared the artifact
    threshold); everything else asks for review.
    """
    if not result.ok:
        return []
    created_at = now or datetime.now(timezone.utc)
    run_uuid: Optional[UUID] = None
    if ingestion_run_id:
        try:
            run_uuid = UUID(str(ingestion_run_id))
        except ValueError:
            run_uuid = None
    tenant_uuid = UUID(str(tenant_id))
    model_name = f"typesafe/{result.evidence.model}" if result.evidence else "typesafe/jev"
    request_id = result.evidence.request_id if result.evidence else None

    artifacts: list[AgentArtifact] = []
    for suggestion in result.suggestions:
        if suggestion.canonical_field is None or suggestion.band is ConfidenceBand.REJECT:
            continue
        artifacts.append(
            AgentArtifact(
                artifact_id=uuid4(),
                artifact_version=AGENT_ARTIFACT_VERSION,
                artifact_type="field_mapping_suggestion",
                tenant_id=tenant_uuid,
                created_at=created_at,
                agent_name=AGENT_NAME,
                agent_version=QUESTIONS_VERSION,
                model_name=model_name,
                suggestion=(
                    f"Map CSV column '{suggestion.source_header}' to {suggestion.canonical_field} "
                    f"({'applied' if suggestion.applied else 'advisory'}, confidence {suggestion.confidence:.2f})."
                ),
                confidence=suggestion.confidence,
                requires_human_review=not suggestion.applied,
                context=AgentArtifactContext(
                    ingestion_run_id=run_uuid,
                    source_hashes=[source_hash],
                    request_id=request_id,
                ),
                payload=FieldMappingSuggestionPayload(
                    source_field=suggestion.source_header,
                    source_value=suggestion.sample_value,
                    target_canonical_field=suggestion.canonical_field,
                    normalized_value=None,
                    rationale=_rationale(suggestion, result),
                ),
            )
        )
    return artifacts
