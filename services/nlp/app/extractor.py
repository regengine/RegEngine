from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import regex as re

logger = logging.getLogger(__name__)

OBLIGATION_PATTERN = re.compile(r"\b(shall|must|required to|has to)\b", re.I)
THRESHOLD_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s?(?P<unit>%|percent|basis points|bps|USD|US\$|\$|€|eur|units?)",
    re.I,
)
JURISDICTION_HINTS = re.compile(r"\b(United States|US|USA|European Union|EU|California|New York|San Francisco)\b")
# The inner word run is bounded to {0,5} (at most a six-word name). An
# unbounded ``*`` made failure backtracking superlinear: a long run of plain
# words with no corporate suffix (matched case-insensitively, so ANY words
# qualify) took seconds at a few thousand words and would stall the worker on
# multi-MB documents. Six words covers real names ("Acme Fresh Produce
# Distribution Company LLC"); longer runs still match on their trailing words.
ORGANIZATION_PATTERN = re.compile(
    r"\b([A-Z][\w&'\.]+(?:\s+[A-Z][\w&'\.]+){0,5})\s+(Inc\.?|LLC|Corp\.?|Co\.?|Company|Ltd\.?|Group|Holdings|Foods|Farms|Grocery)\b",
    re.M | re.I,
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

# ---------------------------------------------------------------------------
# Negation scope (#2942)
# ---------------------------------------------------------------------------
# A PROHIBITED verdict covers two regulatory constructs whose canonical
# ObligationType is *opposite*:
#
#   prohibition  "the handler shall not exceed", "no person shall introduce"
#                — the conduct is banned                       → MUST_NOT
#   exemption    "small farms are not required to file",
#                "shall not be required to maintain", "exempt from"
#                — the duty is lifted, the conduct stays legal → MAY
#
# Typing an exemption MUST_NOT forbids conduct the regulation merely stopped
# mandating; that is the same inversion as typing a prohibition MUST, in the
# other direction. ``negation_scope`` on the verdict lets the conversion layer
# tell them apart without re-deriving modality itself.
#
# Exemptions are matched FIRST because "shall not be required to" contains
# "shall not": phrase order, not sentence order, decides the reading.
_EXEMPTION_PATTERNS = re.compile(
    r"""(?xi)
    \b(?:
        (?:shall|must|may|will|would|is|are|was|were|do|does|did)\s+not\s+
            (?:be\s+)?(?:required|obligated|obliged|compelled|expected)
      | not\s+required
      | need\s+not
      | no\s+obligation
      | exempt(?:ion)?\s+from
      | (?:does|do|did)\s+not\s+(?:require|need)
      # "no person shall be required to ..." — nobody has to, so the duty is
      # lifted rather than the conduct banned.
      | no\s+(?:\w+\s+){0,3}?(?:shall|may|must|will)\s+be\s+
            (?:required|obligated|obliged|compelled|expected)
    )\b
    """
)

# Bans. The "no <actor> shall/may" branch is deliberately keyed to an actor
# noun: a bare "no ... shall" would swallow "no later than X, the firm shall
# file" and "no fewer than two records shall be retained", which are mandates.
_PROHIBITION_PATTERNS = re.compile(
    r"""(?xi)
    (?:
        \b(?:shall|must|may|can|will)\s+not\b
      | \b(?:shall|must|may)\s+never\b
      | \b(?:is|are|was|were)\s+(?:prohibited|forbidden|barred|banned)\b
      | \b(?:is|are)\s+not\s+(?:permitted|allowed)\b
      | \bno\s+(?:person|persons|entity|entities|facility|facilities
                |firm|firms|establishment|establishments|individual|individuals
                |operator|operators|supplier|suppliers|distributor|distributors
                |retailer|retailers|manufacturer|manufacturers|carrier|carriers
                |importer|importers|shipper|shippers|company|companies|one)\b
            (?:\s+\w+){0,3}?\s+(?:shall|may|must|will)\b
    )
    """
)


# ---------------------------------------------------------------------------
# Operative vs attributive "required" (#3009)
# ---------------------------------------------------------------------------
# "required" only expresses the sentence's own modality when it is the
# predicate: "you are required to register", "records are required to be
# maintained". As an attributive participle — "the required records",
# "information required to be maintained under this subpart" — it names a
# duty defined *elsewhere*, and the modal governing the main verb decides
# this sentence's modality.
#
# A be-verb immediately before "required" marks the operative use. "required
# to" alone does NOT: 21 CFR 1.1455(a)(1) has "electronic links to the
# information required to be maintained under this subpart" as a reduced
# relative clause sitting under a permissive "may include".
_OPERATIVE_REQUIRED_PATTERN = re.compile(
    r"\b(?:am|is|are|was|were|be|being|been)\s+required\b",
    re.I,
)


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
        ``negation_scope`` – ``"prohibition"`` (conduct banned) or
                             ``"exemption"`` (duty lifted) when
                             ``obligation`` is PROHIBITED, else ``None``
                             (#2942). The two map to opposite canonical
                             ObligationTypes, so consumers must not collapse
                             them.

    Rules (applied in order):
    0. Exemption phrasings ("not required", "shall not be required to",
       "no obligation", "exempt from", "does not require") → PROHIBITED with
       ``negation_scope="exemption"``. Checked before the ban phrasings
       because "shall not be required to" contains "shall not".
    1. Ban phrasings ("shall not", "must not", "may not", "is prohibited",
       "no person shall") → PROHIBITED with ``negation_scope="prohibition"``.
    2. Conditional hedge ("unless", "except", "exempt") alongside a
       mandatory keyword → CONDITIONAL (WARNING logged).
    3. Mandatory modals ("shall", "must") and the *operative* use of
       "required" ("is required", "are required to register") without
       negation → MANDATORY. #3009: an attributive "required" ("the
       required records") no longer short-circuits here — the modal
       governing the main verb is evaluated first (phase 4), and the bare
       keyword only decides when no permissive modal governs (phase 4b).
    4. Permissive keywords ("may", "can") without negation → PERMITTED.
    4b. Attributive "required" with no governing permissive modal
        → MANDATORY.
    5. Negated permissive ("may not") caught by phase 1.
    6. Fallback → MANDATORY (conservative default).
    """
    if not isinstance(text, str):
        raise TypeError(f"infer_obligation_type requires str, got {type(text).__name__}")
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

    # --- Phase 0: exemption phrasings — the duty is lifted (#2942) -----------
    if _EXEMPTION_PATTERNS.search(text):
        return {
            "obligation": "PROHIBITED",
            "negation_detected": True,
            "negation_scope": "exemption",
        }

    # --- Phase 1: explicit ban phrasings (highest priority) ------------------
    if _PROHIBITION_PATTERNS.search(text):
        return {
            "obligation": "PROHIBITED",
            "negation_detected": True,
            "negation_scope": "prohibition",
        }

    # --- Phase 2: conditional hedge ------------------------------------------
    _MANDATORY_KW = ["shall", "must", "required"]
    has_mandatory = any(kw in text_lower for kw in _MANDATORY_KW)
    if has_mandatory and _CONDITIONAL_PATTERNS.search(text):
        logger.warning(
            "obligation_type CONDITIONAL inferred from hedge phrase",
            extra={"text_snippet": text[:120]},
        )
        return {
            "obligation": "CONDITIONAL",
            "negation_detected": False,
            "negation_scope": None,
        }

    # --- Phase 3: positive mandatory keywords --------------------------------
    # #3009: a mandatory *keyword* must not outrank the modal governing the
    # main verb. "You may keep the required records in electronic form."
    # grants a choice about format — "required" describes the records, not
    # the action the modal governs — so matching it here manufactured an
    # obligation the regulation left optional. Phase 3 claims MANDATORY only
    # for the unambiguous mandatory modals and for the operative use of
    # "required"; an attributive "required" defers to phase 4 and is picked
    # up by phase 4b when no permissive modal governs the sentence.
    for kw in ("shall", "must"):
        if kw in text_lower and not _has_negation_near(kw):
            return {
                "obligation": "MANDATORY",
                "negation_detected": False,
                "negation_scope": None,
            }
    if _OPERATIVE_REQUIRED_PATTERN.search(text) and not _has_negation_near("required"):
        return {
            "obligation": "MANDATORY",
            "negation_detected": False,
            "negation_scope": None,
        }

    # --- Phase 4: positive permissive keywords --------------------------------
    _PERMISSIVE_KW = ["may", "can", "permitted", "allowed"]
    for kw in _PERMISSIVE_KW:
        if kw in text_lower and not _has_negation_near(kw):
            return {
                "obligation": "PERMITTED",
                "negation_detected": False,
                "negation_scope": None,
            }

    # --- Phase 4b: attributive "required" with no governing permissive modal --
    # The keyword is the only modality signal left, so the pre-#3009 reading
    # stands: sentences where "required" IS the operative word ("the required
    # records: lot code, quantity, and date") remain MANDATORY.
    if "required" in text_lower and not _has_negation_near("required"):
        return {
            "obligation": "MANDATORY",
            "negation_detected": False,
            "negation_scope": None,
        }

    # --- Phase 5: negated permissive → PROHIBITED ----------------------------
    for kw in _PERMISSIVE_KW:
        if kw in text_lower and _has_negation_near(kw):
            return {
                "obligation": "PROHIBITED",
                "negation_detected": True,
                "negation_scope": "prohibition",
            }

    # --- Fallback -------------------------------------------------------------
    return {"obligation": "MANDATORY", "negation_detected": False, "negation_scope": None}


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
        raise TypeError(f"extract_entities requires str, got {type(text).__name__}")

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
                    # #2942 — ban vs lifted duty; the conversion layer maps
                    # these onto opposite ObligationTypes.
                    "negation_scope": modality.get("negation_scope"),
                },
            }
        )

    for match in THRESHOLD_PATTERN.finditer(text):
        raw_unit = match.group("unit")
        normalized_unit = UNIT_NORMALIZATION.get(raw_unit.lower(), raw_unit.lower())
        val = float(match.group("value"))
        if not math.isfinite(val):
            # A digit run hundreds of digits long overflows to inf, which
            # serializes as nonstandard JSON ("Infinity") and poisons numeric
            # columns downstream. No real threshold looks like that, so drop
            # the entity rather than propagate a non-finite value.
            continue
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
    _ALL_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
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
            facts.append(
                {
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
                    },
                }
            )

    return facts
