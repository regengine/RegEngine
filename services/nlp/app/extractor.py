from __future__ import annotations

from typing import Dict, List

import regex as re

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


def extract_entities(text: str) -> List[Dict]:
    ents: List[Dict] = []
    for match in OBLIGATION_PATTERN.finditer(text):
        start_sentence = max(text.rfind(".", 0, match.start()) + 1, 0)
        end_sentence = text.find(".", match.end())
        if end_sentence == -1:
            end_sentence = min(len(text), match.end() + 200)
        span_text = text[start_sentence:end_sentence].strip()
        ents.append(
            {
                "type": "OBLIGATION",
                "text": span_text,
                "start": start_sentence,
                "end": end_sentence,
                "attrs": {},
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
    date_pattern = re.compile(r"\b(January|July)\s+\d{1,2},\s+\d{4}\b", re.I)
    
    # Context pattern to ensure it's a compliance date
    context_window_size = 100
    
    for match in date_pattern.finditer(text):
        # Check context for "Compliance Date" or "Enforcement"
        start = max(0, match.start() - context_window_size)
        end = min(len(text), match.end() + context_window_size)
        context = text[start:end].lower()
        
        if "compliance date" in context or "enforcement" in context:
            facts.append({
                "type": "REGULATORY_DATE",
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "attrs": {
                    "key": "Compliance Date",
                    "value": match.group(0),
                    "context": "FDA enforcement posture",
                    "provenance": "FSMA Rule Text"
                }
            })
            
    return facts
