from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List, Optional

os.environ.setdefault("USER_AGENT", "RegEngine/1.0 (+https://regengine.com)")

# Note: These imports require langchain, pypdf, docx2txt, and langchain-groq to be installed
try:
    # Try modern namespace (0.1.0+)
    from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader, Docx2txtLoader, BSHTMLLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_core.prompts import PromptTemplate
    try:
        from langchain_groq import ChatGroq
    except ImportError:
        ChatGroq = None
    LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        # Fallback to legacy namespace (<0.1.0)
        from langchain.document_loaders import PyPDFLoader, WebBaseLoader, Docx2txtLoader, BSHTMLLoader
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain.prompts import PromptTemplate
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            ChatGroq = None
        LANGCHAIN_AVAILABLE = True
    except ImportError:
        LANGCHAIN_AVAILABLE = False


class RegulationParser:
    def __init__(self):
        self.llm = None
        if LANGCHAIN_AVAILABLE and ChatGroq and os.getenv("GROQ_API_KEY"):
            try:
                self.llm = ChatGroq(model="grok-beta", temperature=0)
            except Exception:
                self.llm = None

    async def parse(self, source: str, source_type: str = "pdf") -> List[Dict[str, Any]]:
        """Return list of codified sections: {section_id, title, text, citations, obligations, penalties, jurisdiction, effective_date, content_hash}"""
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("langchain and its loaders are required for regulation parsing")

        if source_type == "pdf":
            loader = PyPDFLoader(source)
        elif source_type == "docx":
            loader = Docx2txtLoader(source)
        elif source_type == "url":
            loader = WebBaseLoader(source)
        elif source_type == "html":
            loader = BSHTMLLoader(source)
        else:
            raise ValueError(f"Unsupported source_type: {source_type}")

        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        chunks = splitter.split_documents(docs)

        sections = []
        seen_hashes = set()

        for chunk in chunks:
            text = chunk.page_content.strip()
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            if content_hash in seen_hashes:
                continue  # deduplicate
            seen_hashes.add(content_hash)

            # Rule-based extraction
            section_match = re.search(r"(?i)(?:section|§|part)\s*([\d.]+)", text)
            section_id = section_match.group(1) if section_match else "unknown"

            # LLM semantic extraction
            obligations = []
            penalties = []
            if self.llm and len(text) > 500:
                try:
                    prompt = PromptTemplate.from_template(
                        "Extract from this regulation text:\n"
                        "1. Obligations (shall/must/required)\n"
                        "2. Penalties\n"
                        "Return only the extracted items as a bulleted list, grouped by category.\n"
                        "Text: {text}"
                    )
                    # Use invoke instead of run
                    response = self.llm.invoke(prompt.format(text=text[:4000]))
                    result = response.content if hasattr(response, 'content') else str(response)
                    
                    lines = result.split("\n")
                    current_category = None
                    for line in lines:
                        line = line.strip().lower()
                        if "obligation" in line:
                            current_category = "obligations"
                            continue
                        elif "penalty" in line or "penalties" in line:
                            current_category = "penalties"
                            continue
                        
                        if line.startswith(("-", "*", "•", "1.", "2.", "3.", "4.", "5.")):
                            item = line.lstrip("-*•12345. ").strip()
                            if item:
                                if current_category == "obligations":
                                    obligations.append(item)
                                elif current_category == "penalties":
                                    penalties.append(item)
                except Exception:
                    obligations = extract_requirements(text)
                    penalties = []
            else:
                obligations = extract_requirements(text)
                penalties = []

            sections.append(
                {
                    "section_id": section_id,
                    "title": text[:200].strip().split("\n")[0],
                    "text": text,
                    "citations": extract_citations(text),
                    "obligations": obligations,
                    "penalties": penalties,
                    "jurisdiction": self._detect_jurisdiction(text),
                    "effective_date": self._extract_date(text),
                    "content_hash": content_hash,
                }
            )
        return sections

    def _detect_jurisdiction(self, text: str) -> str:
        """Detect jurisdiction based on keywords."""
        if any(k in text for k in ("FDA", "21 CFR", "Food and Drug Administration", "FSMA")):
            return "FDA"
        if any(k in text for k in ("CFR", "Code of Federal Regulations")):
            return "US-FEDERAL"
        return "UNKNOWN"

    def _extract_date(self, text: str) -> Optional[str]:
        """Extract effective or dated date."""
        match = re.search(r"(?i)(?:effective|dated)\s+(?:on\s+)?(\d{1,2}/\d{1,2}/\d{4})", text)
        if not match:
            # Try ISO format or similar
            match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        return match.group(1) if match and match.groups() else (match.group(0) if match else None)


def extract_citations(text: str) -> List[str]:
    """Extract common legal citations using regex."""
    return list(set(re.findall(r"(?i)(§?\s*[\d.]+|\d+\s+CFR\s+[\d.]+)", text)))


def extract_requirements(text: str) -> List[str]:
    """Identify requirement sentences based on modal verbs."""
    return [
        sent.strip()
        for sent in text.split(".")
        if any(k in sent.lower() for k in ("shall", "must", "required", "obligated", "mandatory"))
    ]
