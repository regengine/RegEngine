"""Deterministic extractor registry for provenance and replay flows."""

from .dora_extractor import DORAExtractor
from .llm_extractor import LLMGenerativeExtractor
from .nydfs_extractor import NYDFSExtractor
from .sec_sci_extractor import SECSCIExtractor

# Hard-coded registry ensures replay tooling can map framework identifiers to
# concrete extractor classes without resorting to dynamic imports.
EXTRACTOR_REGISTRY = {
    "DORA": DORAExtractor,
    "US-SEC-SCI": SECSCIExtractor,
    "US-NY-500": NYDFSExtractor,
    "GENERIC": LLMGenerativeExtractor,
}


def get_extractor(framework_name: str):
    """Instantiate an extractor deterministically based on framework code."""

    extractor_cls = EXTRACTOR_REGISTRY.get(framework_name)
    if extractor_cls is None:
        raise ValueError(f"Unknown extractor framework: {framework_name}")
    return extractor_cls()


__all__ = [
    "DORAExtractor",
    "LLMGenerativeExtractor",
    "NYDFSExtractor",
    "SECSCIExtractor",
    "EXTRACTOR_REGISTRY",
    "get_extractor",
]
