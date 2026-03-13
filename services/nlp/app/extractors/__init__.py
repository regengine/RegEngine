"""Deterministic extractor registry for provenance and replay flows."""

from .fsma_extractor import FSMAExtractor
from .llm_extractor import LLMGenerativeExtractor

# Hard-coded registry ensures replay tooling can map framework identifiers to
# concrete extractor classes without resorting to dynamic imports.
EXTRACTOR_REGISTRY = {
    "FSMA-204": FSMAExtractor,
    "GENERIC": LLMGenerativeExtractor,
}


def get_extractor(framework_name: str):
    """Instantiate an extractor deterministically based on framework code."""

    extractor_cls = EXTRACTOR_REGISTRY.get(framework_name)
    if extractor_cls is None:
        raise ValueError(f"Unknown extractor framework: {framework_name}")
    return extractor_cls()


__all__ = [
    "FSMAExtractor",
    "LLMGenerativeExtractor",
    "EXTRACTOR_REGISTRY",
    "get_extractor",
]
