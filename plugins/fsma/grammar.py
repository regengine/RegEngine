"""
FSMA Regulatory Grammar
=======================
Statutory extraction patterns for FDA FSMA 204.
"""

FSMA_GRAMMAR = {
    "cte_patterns": [
        r"(?i)critical tracking event",
        r"(?i)receiving",
        r"(?i)transformation",
        r"(?i)creation",
        r"(?i)shipping",
        r"(?i)initial packing",
    ],
    "kde_patterns": {
        "lot_number": [r"(?i)traceability lot code", r"(?i)lot number"],
        "location_id": [r"(?i)location identifier", r"(?i)facility id"],
        "product_description": [r"(?i)product description", r"(?i)commodity"],
        "quantity": [r"(?i)quantity", r"(?i)amount", r"(?i)weight"],
        "uom": [r"(?i)unit of measure", r"(?i)uom"],
    },
    "obligation_keywords": [
        "must maintain",
        "shall provide",
        "required to record",
        "within 24 hours",
    ]
}

def identify_fsma_elements(text: str) -> dict:
    """Identify FSMA-specific elements in a text chunk."""
    import re
    
    found_ctes = []
    for pattern in FSMA_GRAMMAR["cte_patterns"]:
        if re.search(pattern, text):
            found_ctes.append(pattern.replace("(?i)", ""))
            
    found_kdes = []
    for kde, patterns in FSMA_GRAMMAR["kde_patterns"].items():
        for pattern in patterns:
            if re.search(pattern, text):
                found_kdes.append(kde)
                break
                
    return {
        "ctes": list(set(found_ctes)),
        "kdes": list(set(found_kdes)),
        "is_fsma_related": len(found_ctes) > 0 or len(found_kdes) > 0
    }
