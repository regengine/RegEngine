#!/usr/bin/env python3
"""
RegEngine Regulatory Document Ingestion Script

Automates the ingestion of regulatory documents into the RegEngine platform.
Supports PDF documents from various regulatory authorities.

Usage:
    # Ingest NYDFS Part 500
    python scripts/ingest_document.py \\
        --file docs/regulations/NYDFS_Part500.pdf \\
        --jurisdiction US-NY \\
        --title "NYDFS Part 500 Cybersecurity Requirements" \\
        --document-type REGULATION \\
        --effective-date 2017-03-01

    # Ingest DORA
    python scripts/ingest_document.py \\
        --url https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554 \\
        --jurisdiction EU \\
        --title "Digital Operational Resilience Act" \\
        --document-type REGULATION \\
        --effective-date 2025-01-17

    # Ingest with automatic extraction
    python scripts/ingest_document.py \\
        --file SEC_Regulation_SCI.pdf \\
        --jurisdiction US-SEC \\
        --title "Regulation SCI" \\
        --document-type REGULATION \\
        --extract \\
        --extractor sec_sci
"""

import argparse
import sys
import os
import hashlib
import requests
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, UUID
from typing import Optional
from tqdm import tqdm

# Calculate project root relative to this script
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from services.nlp.app.extractors import NYDFSExtractor, DORAExtractor, SECSCIExtractor


class DocumentIngestion:
    """Handles regulatory document ingestion workflow."""

    EXTRACTORS = {
        "nydfs": NYDFSExtractor,
        "dora": DORAExtractor,
        "sec_sci": SECSCIExtractor,
    }

    def __init__(self, tenant_id: Optional[UUID] = None):
        """
        Initialize document ingestion.

        Args:
            tenant_id: Optional tenant UUID. If None, uses global tenant.
        """
        self.tenant_id = tenant_id or UUID("00000000-0000-0000-0000-000000000001")

    def ingest_document(
        self,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        jurisdiction: str = "",
        title: str = "",
        document_type: str = "REGULATION",
        effective_date: Optional[str] = None,
        extract: bool = False,
        extractor_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Ingest a regulatory document into RegEngine.

        Args:
            file_path: Path to local PDF file
            url: URL to download document from
            jurisdiction: Regulatory jurisdiction (US-NY, EU, US-SEC, etc.)
            title: Document title
            document_type: Type of document (REGULATION, GUIDANCE, etc.)
            effective_date: Effective date in YYYY-MM-DD format
            extract: Whether to run NLP extraction immediately
            extractor_name: Name of extractor to use (nydfs, dora, sec_sci)
            dry_run: If True, simulate ingestion without processing

        Returns:
            dict with document_id, content_hash, and extraction results
        """
        if dry_run:
            print(f"🔍 [DRY RUN] Would ingest document: {title}")
            print(f"   Jurisdiction: {jurisdiction}")
            print(f"   Type: {document_type}")
            if file_path:
                print(f"   Source: File {file_path}")
            elif url:
                print(f"   Source: URL {url}")
            if extract:
                print(f"   Extraction: {extractor_name}")
            return {
                "document_id": "dry-run-id",
                "content_hash": "dry-run-hash",
                "extractions_count": 0,
                "extractions": []
            }

        print(f"📄 Ingesting document: {title}")
        print(f"   Jurisdiction: {jurisdiction}")
        print(f"   Type: {document_type}")

        # Step 1: Obtain document content
        if file_path:
            content = self._read_file(file_path)
            source = file_path
        elif url:
            content = self._download_file(url)
            source = url
        else:
            raise ValueError("Must provide either file_path or url")

        # Step 2: Calculate content hash
        content_hash = self._calculate_hash(content)
        print(f"   Content hash: {content_hash[:16]}...")

        # Step 3: Extract text (if PDF)
        if source.lower().endswith('.pdf'):
            text = self._extract_pdf_text(content)
        else:
            text = content.decode('utf-8') if isinstance(content, bytes) else content

        print(f"   Extracted {len(text)} characters")

        # Step 4: Create document record
        document_id = uuid4()
        document_record = {
            "id": str(document_id),
            "title": title,
            "jurisdiction": jurisdiction,
            "document_type": document_type,
            "effective_date": effective_date,
            "content_hash": content_hash,
            "source": source,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": str(self.tenant_id),
        }

        print(f"   Document ID: {document_id}")

        # Step 5: Run NLP extraction (if requested)
        extractions = []
        if extract and extractor_name:
            print(f"\n🔍 Running {extractor_name.upper()} extraction...")
            extractions = self._run_extraction(
                text, document_id, extractor_name
            )
            print(f"   Extracted {len(extractions)} obligations")

            # Show sample extractions
            if extractions:
                print(f"\n   Sample extractions:")
                for i, ext in enumerate(extractions[:3], 1):
                    print(f"   {i}. {ext.provision_text[:80]}...")
                    print(f"      Type: {ext.obligation_type.value}, "
                          f"Confidence: {ext.confidence_score:.2f}")

        return {
            "document_id": str(document_id),
            "content_hash": content_hash,
            "extractions_count": len(extractions),
            "extractions": [
                {
                    "provision_hash": ext.provision_hash,
                    "text": ext.provision_text,
                    "obligation_type": ext.obligation_type.value,
                    "confidence": ext.confidence_score,
                }
                for ext in extractions
            ]
        }

    def _read_file(self, file_path: str) -> bytes:
        """Read file content from local filesystem."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, 'rb') as f:
            return f.read()

    def _download_file(self, url: str) -> bytes:
        """Download file from URL."""
        print(f"   Downloading from {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content

    def _calculate_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    def _extract_pdf_text(self, content: bytes) -> str:
        """
        Extract text from PDF content using pypdf.

        Falls back to pdfplumber if pypdf fails, then to placeholder if both fail.
        """
        import io

        # Try pypdf first (fast, lightweight)
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

            if pages_text:
                extracted_text = "\n\n".join(pages_text)
                print(f"   [pypdf] Extracted {len(extracted_text)} characters from {len(reader.pages)} pages")
                return extracted_text
        except ImportError:
            pass  # pypdf not installed, try next method
        except Exception as e:
            print(f"   [pypdf] Extraction failed: {str(e)[:100]}, trying alternative...")

        # Try pdfplumber as fallback (more robust for complex PDFs)
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)

                if pages_text:
                    extracted_text = "\n\n".join(pages_text)
                    print(f"   [pdfplumber] Extracted {len(extracted_text)} characters from {len(pdf.pages)} pages")
                    return extracted_text
        except ImportError:
            pass  # pdfplumber not installed
        except Exception as e:
            print(f"   [pdfplumber] Extraction failed: {str(e)[:100]}")

        # Final fallback: return placeholder with warning
        print("   ⚠️  WARNING: PDF extraction libraries not available, using placeholder")
        print("   Install with: pip install pypdf pdfplumber")
        return f"[PDF content - {len(content)} bytes - extraction libraries not available]\n\nTo enable PDF text extraction, install pypdf or pdfplumber."

    def _run_extraction(
        self,
        text: str,
        document_id: UUID,
        extractor_name: str
    ):
        """
        Run NLP extraction using specified extractor.

        Args:
            text: Document text
            document_id: Document UUID
            extractor_name: Name of extractor (nydfs, dora, sec_sci)

        Returns:
            List of ExtractionPayload objects
        """
        if extractor_name not in self.EXTRACTORS:
            raise ValueError(
                f"Unknown extractor: {extractor_name}. "
                f"Available: {list(self.EXTRACTORS.keys())}"
            )

        extractor_class = self.EXTRACTORS[extractor_name]
        extractor = extractor_class()

        extractions = extractor.extract_obligations(
            text=text,
            document_id=document_id,
            tenant_id=self.tenant_id,
        )

        return extractions


def main():
    """Main entry point for document ingestion."""
    parser = argparse.ArgumentParser(
        description="Ingest regulatory documents into RegEngine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Document source
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file",
        type=str,
        help="Path to local document file (PDF)"
    )
    source_group.add_argument(
        "--url",
        type=str,
        help="URL to download document from"
    )
    source_group.add_argument(
        "--directory",
        type=str,
        help="Path to directory containing PDF files for batch ingestion"
    )

    # Document metadata
    parser.add_argument(
        "--jurisdiction",
        type=str,
        required=True,
        help="Regulatory jurisdiction (e.g., US-NY, EU, US-SEC)"
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Document title (required for single file/url, ignored for directory)"
    )
    parser.add_argument(
        "--document-type",
        type=str,
        default="REGULATION",
        help="Document type (REGULATION, GUIDANCE, etc.)"
    )
    parser.add_argument(
        "--effective-date",
        type=str,
        help="Effective date (YYYY-MM-DD)"
    )

    # Extraction options
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Run NLP extraction immediately"
    )
    parser.add_argument(
        "--extractor",
        type=str,
        choices=["nydfs", "dora", "sec_sci"],
        help="Extractor to use for NLP extraction"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate ingestion without processing"
    )

    # Tenant context
    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Tenant UUID (default: global tenant)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.directory and not args.title:
        parser.error("--title is required when using --file or --url")
    
    if args.extract and not args.extractor:
        parser.error("--extractor is required when --extract is specified")

    # Parse tenant ID
    tenant_id = None
    if args.tenant_id:
        try:
            tenant_id = UUID(args.tenant_id)
        except ValueError:
            print(f"❌ Error: Invalid tenant UUID: {args.tenant_id}")
            sys.exit(1)

    # Run ingestion
    try:
        ingestion = DocumentIngestion(tenant_id=tenant_id)
        
        if args.directory:
            dir_path = Path(args.directory)
            if not dir_path.exists() or not dir_path.is_dir():
                print(f"❌ Error: Directory not found: {args.directory}")
                sys.exit(1)
            
            files = list(dir_path.glob("*.pdf"))
            if not files:
                print(f"⚠️ No PDF files found in {args.directory}")
                sys.exit(0)
                
            print(f"🚀 Starting batch ingestion of {len(files)} files from {args.directory}")
            
            success_count = 0
            for file_path in tqdm(files, desc="Ingesting documents"):
                try:
                    # Use filename as title for batch ingestion
                    doc_title = file_path.stem.replace("_", " ").title()
                    
                    ingestion.ingest_document(
                        file_path=str(file_path),
                        jurisdiction=args.jurisdiction,
                        title=doc_title,
                        document_type=args.document_type,
                        effective_date=args.effective_date,
                        extract=args.extract,
                        extractor_name=args.extractor,
                        dry_run=args.dry_run
                    )
                    success_count += 1
                except Exception as e:
                    print(f"\n❌ Failed to ingest {file_path.name}: {e}")
            
            print(f"\n✅ Batch ingestion complete! ({success_count}/{len(files)} successful)")
            
        else:
            # Single file/URL ingestion
            result = ingestion.ingest_document(
                file_path=args.file,
                url=args.url,
                jurisdiction=args.jurisdiction,
                title=args.title,
                document_type=args.document_type,
                effective_date=args.effective_date,
                extract=args.extract,
                extractor_name=args.extractor,
                dry_run=args.dry_run
            )

            if args.dry_run:
                print(f"\n✅ Dry run complete!")
            else:
                print(f"\n✅ Document ingested successfully!")
                print(f"   Document ID: {result['document_id']}")
                print(f"   Content Hash: {result['content_hash']}")
                if result['extractions_count'] > 0:
                    print(f"   Extractions: {result['extractions_count']}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
