"""Sources module."""

from .base import SourceAdapter
from .federal_register import FederalRegisterAdapter
from .ecfr import ECFRAdapter
from .fda import FDAAdapter
from .fsma_204 import FSMA204Adapter

__all__ = [
    "SourceAdapter",
    "FederalRegisterAdapter",
    "ECFRAdapter",
    "FDAAdapter",
    "FSMA204Adapter",
]
