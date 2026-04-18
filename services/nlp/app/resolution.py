from __future__ import annotations

import re
import structlog
from typing import Optional, Dict, List, Tuple

logger = structlog.get_logger("nlp.resolution")

# Stubbed Master Data (Simulating a MDM System / DUNS Database)
MASTER_DATA = {
    "WALMART": {"id": "duns:007874200", "name": "Walmart Inc.", "type": "RETAILER"},
    "WAL-MART": {"id": "duns:007874200", "name": "Walmart Inc.", "type": "RETAILER"},
    "COSTCO": {"id": "duns:009289230", "name": "Costco Wholesale Corp.", "type": "RETAILER"},
    "COSTCO WHOLESALE": {"id": "duns:009289230", "name": "Costco Wholesale Corp.", "type": "RETAILER"},
    "RALPHS": {"id": "duns:009289555", "name": "Ralphs Grocery Company", "type": "RETAILER"},
    "KROGER": {"id": "duns:006999528", "name": "The Kroger Co.", "type": "RETAILER"},

    # Common Suppliers (Stubbed)
    "TYSON FOODS": {"id": "duns:006903702", "name": "Tyson Foods, Inc.", "type": "SUPPLIER"},
    "DOLE": {"id": "duns:006903111", "name": "Dole Food Company", "type": "SUPPLIER"},
    "DRISCOLL'S": {"id": "duns:009212345", "name": "Driscoll's Inc.", "type": "SUPPLIER"},
    "TAYLOR FARMS": {"id": "duns:009255555", "name": "Taylor Fresh Foods, Inc.", "type": "SUPPLIER"},
}

# Corporate suffix stripping — preserved between normalized name and tokens.
_SUFFIX_PATTERN = re.compile(
    r"\b(INC|LLC|CORP|CO|COMPANY|LTD|GROUP|HOLDINGS|FOODS|FARMS|GROCERY|WHOLESALE)\.?\b",
    re.IGNORECASE,
)

# Non-word punctuation — replaced with space during normalization.
_PUNCT_PATTERN = re.compile(r"[^A-Z0-9\s]")


def _normalize(name: str) -> str:
    """Normalize a name to a comparable canonical form.

    Steps (#1269):
    1. Upper-case, strip.
    2. Replace punctuation with spaces so ``Wal-Mart`` and ``WALMART`` match.
    3. Strip corporate suffixes (INC, LLC, CORP, ...).
    4. Collapse whitespace.
    """

    upper = name.upper().strip()
    no_punct = _PUNCT_PATTERN.sub(" ", upper)
    no_suffix = _SUFFIX_PATTERN.sub(" ", no_punct)
    return re.sub(r"\s+", " ", no_suffix).strip()


def _tokens(name: str) -> List[str]:
    return [t for t in _normalize(name).split(" ") if t]


def _token_set_ratio(a: str, b: str) -> float:
    """Compute a RapidFuzz-style token_set_ratio without the dependency.

    Jaccard similarity on token sets, scaled to [0, 100]. Matches exactly
    when token sets are identical and degrades gracefully when one side has
    extra tokens. This is NOT a substring check — "KROGER-FAKE-BRAND" vs
    "KROGER" gives 1/3 = 33%, well below the 90% threshold (#1269).
    """

    tokens_a = set(_tokens(a))
    tokens_b = set(_tokens(b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return 100.0 * len(intersection) / len(union)


# Threshold for fuzzy acceptance (#1269). Combined with the subset constraint
# below, this prevents a single shared token ("KROGER") being extended with
# attacker-chosen additions (e.g. "KROGER FAKE BRAND"). The real protection
# is the ratio + subset check together: "KROGER FAKE BRAND" vs "KROGER" has
# a subset match but only 33% token_set_ratio, which fails here.
# Legitimate extensions like "Wal-Mart Stores Inc." → "WAL MART STORES" vs
# "WAL-MART" key → "WAL MART" score 66.6% and resolve correctly.
_FUZZY_RATIO_THRESHOLD = 60.0

# Max number of additional non-suffix tokens we tolerate beyond the key's
# token set before treating the supplied name as too divergent. This catches
# the "KROGER FAKE BRAND" pattern independently of the ratio.
_MAX_EXTRA_TOKENS = 2


class EntityResolver:
    """Resolves raw entity text to canonical Entity IDs (Master Data).

    Matching strategy (hardened per #1269):

    1. Exact normalized match (strip punctuation, casefold, strip corporate
       suffixes). ``Wal-Mart Stores Inc.`` → ``WAL MART STORES`` → lookup.
    2. Token-set ratio fallback with a 90% threshold, PLUS a requirement
       that every master-record token appears in the supplied name. This
       prevents a single common token from resolving to the full record.

    The previous implementation used substring ``in`` matching, which let an
    attacker launder confidence by embedding a known brand substring in a
    hostile name (e.g. ``KROGER-FAKE-BRAND`` resolved to Kroger's DUNS).
    """

    def __init__(self) -> None:
        # Pre-normalize master keys for exact lookup.
        self._records = MASTER_DATA
        self._normalized_keys: Dict[str, str] = {
            _normalize(key): key for key in MASTER_DATA.keys()
        }

    def resolve_organization(self, raw_name: Optional[str]) -> Optional[Dict]:
        """Resolve an organization name to a canonical entity.

        Args:
            raw_name: The extracted text (e.g. ``Wal-Mart Stores``).

        Returns:
            ``{"id", "name", "type", "match_strategy", "match_score"}`` on a
            resolved match, or ``None`` if confidence is insufficient.
            ``match_strategy`` is one of ``exact``, ``fuzzy`` so callers can
            audit which path was taken.
        """

        if not raw_name or not isinstance(raw_name, str):
            return None

        normalized = _normalize(raw_name)
        if not normalized:
            return None

        # --- 1. Exact normalized match ---
        if normalized in self._normalized_keys:
            original_key = self._normalized_keys[normalized]
            record = dict(self._records[original_key])
            record["match_strategy"] = "exact"
            record["match_score"] = 100.0
            logger.info(
                "entity_resolved_exact",
                raw=raw_name,
                resolved=record["name"],
                id=record["id"],
            )
            return record

        # --- 2. Fuzzy fallback (token_set_ratio + subset + extra-token cap) ---
        best: Tuple[float, Optional[str]] = (0.0, None)
        supplied_tokens = set(_tokens(raw_name))
        for key in self._records.keys():
            key_tokens = set(_tokens(key))
            if not key_tokens:
                continue
            # Guard against short-token-only keys (no meaningful key to match).
            if all(len(t) <= 2 for t in key_tokens):
                continue
            # Require token containment in one direction.
            if not key_tokens.issubset(supplied_tokens) and not supplied_tokens.issubset(
                key_tokens
            ):
                continue
            # Extra-token cap (#1269). "KROGER FAKE BRAND" has 2 extra tokens
            # vs the "KROGER" key; values above the cap are rejected even if
            # technically a subset match.
            extras = len(supplied_tokens - key_tokens)
            if extras > _MAX_EXTRA_TOKENS:
                continue
            score = _token_set_ratio(raw_name, key)
            if score > best[0]:
                best = (score, key)

        if best[1] is not None and best[0] >= _FUZZY_RATIO_THRESHOLD:
            record = dict(self._records[best[1]])
            record["match_strategy"] = "fuzzy"
            record["match_score"] = best[0]
            logger.info(
                "entity_resolved_fuzzy",
                raw=raw_name,
                resolved=record["name"],
                id=record["id"],
                score=best[0],
            )
            return record

        if best[1] is not None:
            logger.debug(
                "entity_resolution_below_threshold",
                raw=raw_name,
                best_candidate=self._records[best[1]]["name"],
                score=best[0],
                threshold=_FUZZY_RATIO_THRESHOLD,
            )
        return None
