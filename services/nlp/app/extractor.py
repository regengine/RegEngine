from __future__ import annotations

import logging
from typing import Dict, List, Optional

import regex as re

logger = logging.getLogger(__name__)

OBLIGATION_PATTERN = re.compile(r"\b(shall|must|required to|has to)\b", re.I)
THRESHOLD_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s?(?P<unit>%|percent|basis points|bps|USD|US\$|\$|€|eur|units?)",
    re.I,
)
JURISDICTION_HINTS = re.compile(
    r"\b(United States|US|USA|European Union|EU|California|New York|San Francisco)\b"
)
ORGANIZATION_PATTERN = re.compile(
    r"\b([A-Z][\w&'\.]+(?:\s+[A-Z][\w&'\.]+)*)\s+(Inc\.?|LLC|Corp\.?|Co\.?|Company|Ltd\.?|Group|Holdings|Foods|Farms|Grocery)\b",
    re.M | re.I
)

UNIT_NORMALIZATION = {
    "%": "percent",
    "percent": "percent",
    "basis points": "basis_points",
    "bps": "basis_points",
    "usd": "usd",
    "us$": "usd",
    "$": "usd",
    "€": "eur",
    "eur": "eur",
    "units": "units",
    "unit": "units",
}

# ---------------------------------------------------------------------------
# Negation + modality helpers (#1299)
# ---------------------------------------------------------------------------

# Negation tokens that flip obligation type when found within N tokens of a modal.
_NEGATION_TOKENS: frozenset = frozenset({"not", "no", "never", "without"})

# Conditional hedge phrases — sentence contains both obligation and an escape clause.
_CONDITIONAL_PATTERNS = re.compile(
    r"\b(unless|except|provided that|subject to|exempt(?:ion)?|unless exempt)\b",
    re.I,
)

# Window size (tokens) to check around a modal keyword for negation.
_NEGATION_WINDOW = 5


def _tokenise(text: str) -> list:
    """Whitespace-split, strip trailing punctuation from each token."""
    return [t.strip(".,;:()[]\"'") for t in text.lower().split()]


def infer_obligation_type(text: str) -> dict:
    """Infer obligation modality from *text* using negation-aware token matching.

    Returns a dict with keys:
        ``obligation``  – ``"MANDATORY"``, ``"PROHIBITED"``, ``"PERMITTED"``,
                          or ``"CONDITIONAL"``.
        ``negation_detected`` – ``True`` when a negation token flipped the
                                base modality.

    Rules (applied in order):
    1. Explicit prohibited phrases ("shall not", "must not", "may not",
       "not required", "no obligation", "exempt from", "does not require")
       → PROHIBITED (negation_detected=True).
    2. Conditional hedge ("unless", "except", "exempt") alongside a
       mandatory keyword → CONDITIONAL (WARNING logged).
    3. Mandatory keywords ("shall", "must", "required") without negation
       → MANDATORY.
    4. Permissive keywords ("may", "can") without negation → PERMITTED.
    5. Negated permissive ("may not") caught by phase 1.
    6. Fallback → MANDATORY (conservative default).
    """
    text_lower = text.lower()
    tokens = _tokenise(text)

    def _has_negation_near(keyword: str) -> bool:
        """True if *keyword* has a negation token within _NEGATION_WINDOW tokens."""
        for idx, tok in enumerate(tokens):
            if tok == keyword:
                window_start = max(0, idx - _NEGATION_WINDOW)
                window_end = min(len(tokens), idx + _NEGATION_WINDOW + 1)
                window = set(tokens[window_start:window_end]) - {keyword}
                if window & _NEGATION_TOKENS:
                    return True
        return False

    # --- Phase 1: explicit negated-modal phrases (highest priority) ----------
    _PROHIBITED_PHRASES = [
        "shall not", "must not", "may not", "is not required",
        "not required", "no obligation", "exempt from", "does not require",
        "does not need",
    ]
    for phrase in _PROHIBITED_PHRASES:
        if phrase in text_lower:
            return {"obligation": "PROHIBITED", "negation_detected": True}

    # --- Phase 2: conditional hedge ------------------------------------------
    _MANDATORY_KW = ["shall", "must", "required"]
    has_mandatory = any(kw in text_lower for kw in _MANDATORY_KW)
    if has_mandatory and _CONDITIONAL_PATTERNS.search(text):
        logger.warning(
            "obligation_type CONDITIONAL inferred from hedge phrase",
            extra={"text_snippet": text[:120]},
        )
        return {"obligation": "CONDITIONAL", "negation_detected": False}

    # --- Phase 3: positive mandatory keywords --------------------------------
    for kw in _MANDATORY_KW:
        if kw in text_lower and not _has_negation_near(kw):
            return {"obligation": "MANDATORY", "negation_detected": False}

    # --- Phase 4: positive permissive keywords --------------------------------
    _PERMISSIVE_KW = ["may", "can", "permitted", "allowed"]
    for kw in _PERMISSIVE_KW:
        if kw in text_lower and not _has_negation_near(kw):
            return {"obligation": "PERMITTED", "negation_detected": False}

    # --- Phase 5: negated permissive → PROHIBITED ----------------------------
    for kw in _PERMISSIVE_KW:
        if kw in text_lower and _has_negation_near(kw):
            return {"obligation": "PROHIBITED", "negation_detected": True}

    # --- Fallback -------------------------------------------------------------
    return {"obligation": "MANDATORY", "negation_detected": False}


def extract_entities(text: str) -> List[Dict]:
    """Extract entities from raw text.

    Args:
        text: Document text. ``None`` is rejected with a ``TypeError`` so the
            caller cannot silently treat a missing document as "processed OK,
            nothing to extract" (see #1274).
    """

    if text is None:
        raise TypeError("extract_entities received None; caller must pass a str")
    if not isinstance(text, str):
        raise TypeError(
            f"extract_entities requires str, got {type(text).__name__}"
        )

    ents: List[Dict] = []
    for match in OBLIGATION_PATTERN.finditer(text):
        start_sentence = max(text.rfind(".", 0, match.start()) + 1, 0)
        end_sentence = text.find(".", match.end())
        if end_sentence == -1:
            end_sentence = min(len(text), match.end() + 200)
        span_text = text[start_sentence:end_sentence].strip()
        # Infer obligation type with negation/modality awareness (#1299).
        modality = infer_obligation_type(span_text)
        ents.append(
            {
                "type": "OBLIGATION",
                "text": span_text,
                "start": start_sentence,
                "end": end_sentence,
                "attrs": {
                    "obligation": modality["obligation"],
                    "negation_detected": modality["negation_detected"],
                },
            }
        )

    for match in THRESHOLD_PATTERN.finditer(text):
        raw_unit = match.group("unit")
        normalized_unit = UNIT_NORMALIZATION.get(raw_unit.lower(), raw_unit.lower())
        val = float(match.group("value"))
        ents.append(
            {
                "type": "THRESHOLD",
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "attrs": {
                    "value": val,
                    "unit": raw_unit,
                    "unit_normalized": normalized_unit,
                },
            }
        )

    for match in JURISDICTION_HINTS.finditer(text):
        ents.append(
            {
                "type": "JURISDICTION",
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "attrs": {"name": match.group(0)},
            }
        )

    for match in ORGANIZATION_PATTERN.finditer(text):
        ents.append(
            {
                "type": "ORGANIZATION",
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "attrs": {"name": match.group(0)},
            }
        )

    # FSMA Compliance Date Extraction (User Request: July 2028 update detection)
    fsma_facts = extract_fsma_facts(text)
    ents.extend(fsma_facts)

    return ents


def extract_fsma_facts(text: str) -> List[Dict]:
    """
    Extract specific FSMA regulatory facts, such as compliance dates.

    This enhancement allows the system to detect changes in regulatory timelines
    (e.g., the July 20, 2028 update).
    """
    facts = []

    # Heuristic for Compliance Date
    # Pattern looks for "Compliance Date" vicinity or explicit date formats known for FSMA
    # Regex for "January 20, 2026" or "July 20, 2028"

    # Broad pattern for the date itself
    _ALL_MONTHS = (
        "January|February|March|April|May|June|"
        "July|August|September|October|November|December"
    )
    date_pattern = re.compile(rf"\b({_ALL_MONTHS})\s+\d{{1,2}},\s+\d{{4}}\b", re.I)

    # Context pattern to ensure it's a compliance date
    context_window_size = 100

    for match in date_pattern.finditer(text):
        # Check context for "Compliance Date" or "Enforcement"
        start = max(0, match.start() - context_window_size)
        end = min(len(text), match.end() + context_window_size)
        context = text[start:end].lower()

        cue_distance: Optional[int] = None
        for cue in ("compliance date", "enforcement"):
            cue_idx = context.find(cue)
            if cue_idx != -1:
                abs_cue = start + cue_idx
                # Minimum distance from the cue to either end of the match
                dist = min(
                    abs(match.start() - abs_cue),
                    abs(match.end() - abs_cue),
                )
                cue_distance = dist if cue_distance is None else min(cue_distance, dist)

        if cue_distance is not None:
            facts.append({
                "type": "REGULATORY_DATE",
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "attrs": {
                    "key": "Compliance Date",
                    "value": match.group(0),
                    "context": "FDA enforcement posture",
                    # Provenance is hint-only; downstream scoring must not
                    # trust this label unless the ingestion pipeline signed
                    # the document (#1206).
                    "provenance": "FSMA Rule Text",
                    # Record the proximity distance so the scorer can reward
                    # tighter matches. Previously all matches were rewarded
                    # equally (100-char window).
                    "context_distance": cue_distance,
                }
            })

    return facts
