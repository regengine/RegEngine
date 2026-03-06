from .models import *
from .parser import RegulationParser

# MappingEngine depends on optional ML packages (langchain, langchain_groq).
# Import lazily so that the kernel package is usable without those deps installed.
try:
    from .graph import MappingEngine
except ImportError:
    MappingEngine = None  # type: ignore[assignment,misc]
