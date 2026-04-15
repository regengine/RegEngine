"""
Unit of Measure conversion and CTE lifecycle ordering.

Converts common food industry units to a canonical base unit (lbs).
Used by mass balance evaluator to compare quantities across different UOMs.
"""

from typing import Dict, Optional


_UOM_TO_LBS: Dict[str, float] = {
    # Weight (already in lbs)
    "lbs": 1.0,
    "lb": 1.0,
    "pound": 1.0,
    "pounds": 1.0,
    # Kilograms
    "kg": 2.20462,
    "kgs": 2.20462,
    "kilogram": 2.20462,
    "kilograms": 2.20462,
    # Ounces
    "oz": 0.0625,
    "ounce": 0.0625,
    "ounces": 0.0625,
    # Tons
    "ton": 2000.0,
    "tons": 2000.0,
    "short_ton": 2000.0,
    "metric_ton": 2204.62,
    "mt": 2204.62,
    # Produce containers (industry standard approximations)
    "case": 24.0,
    "cases": 24.0,
    "cs": 24.0,
    "carton": 24.0,
    "cartons": 24.0,
    "bin": 800.0,
    "bins": 800.0,
    "pallet": 2000.0,
    "pallets": 2000.0,
    "crate": 40.0,
    "crates": 40.0,
    "box": 24.0,
    "boxes": 24.0,
    "bag": 5.0,
    "bags": 5.0,
    "bunch": 1.5,
    "bunches": 1.5,
    "head": 2.0,
    "heads": 2.0,
    "each": 1.0,
    "ea": 1.0,
    "unit": 1.0,
    "units": 1.0,
    "piece": 1.0,
    "pieces": 1.0,
    "pc": 1.0,
    "pcs": 1.0,
}


def normalize_to_lbs(quantity: float, uom: str) -> Optional[float]:
    """Convert a quantity to lbs using the UOM lookup table.

    Returns None if the UOM is not recognized.
    """
    uom_key = uom.lower().strip().rstrip(".")
    factor = _UOM_TO_LBS.get(uom_key)
    if factor is None:
        return None
    return quantity * factor


# CTE lifecycle ordering per FSMA 204 supply chain flow
CTE_LIFECYCLE_ORDER = {
    "harvesting": 0,
    "cooling": 1,
    "initial_packing": 2,
    "first_land_based_receiving": 3,
    "transformation": 4,
    "shipping": 5,
    "receiving": 6,
}
