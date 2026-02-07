"""
Authority & Fact Lineage Service

Provides traceability from source authority documents through extracted facts
to compliance verdicts. Creates cryptographic links for audit purposes.
"""

import hashlib
import structlog
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, List, Any, Tuple, Union
from uuid import UUID
from pathlib import Path

logger = structlog.get_logger(__name__)


class AuthorityLineageService:
    """
    Service for managing authority documents, extracted facts, and citations.
    
    Creates a cryptographic traceability chain from source documents
    to compliance verdicts.
    """
    
    def __init__(self, db_session, tenant_id: UUID):
        """
        Initialize the service.
        
        Args:
            db_session: SQLAlchemy database session
            tenant_id: Current tenant ID
        """
        self.db = db_session
        self.tenant_id = tenant_id
    
    # =========================================================================
    # Authority Document Management
    # =========================================================================
    
    def register_authority_document(
        self,
        document_code: str,
        document_name: str,
        document_type: str,
        issuer_name: str,
        effective_date: date,
        issuer_type: Optional[str] = None,
        expiration_date: Optional[date] = None,
        file_path: Optional[str] = None,
        extraction_method: str = "manual",
        extraction_notes: Optional[str] = None,
        ingested_by: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Register a new authority document.
        
        Args:
            document_code: Unique code (e.g., 'SAG_CBA_2023')
            document_name: Human-readable name
            document_type: 'cba', 'statute', 'regulation', 'municipal_code'
            issuer_name: Issuing authority name
            effective_date: When document becomes effective
            issuer_type: 'union', 'government', 'municipality'
            expiration_date: When document expires (optional)
            file_path: Path to original document file
            extraction_method: How document was ingested
            extraction_notes: Notes about ingestion
            ingested_by: User who ingested the document
            
        Returns:
            Dict with created document info
        """
        from .pcos_models import PCOSAuthorityDocumentModel
        from sqlalchemy import select
        
        # Check for existing document
        existing = self.db.execute(
            select(PCOSAuthorityDocumentModel)
            .where(PCOSAuthorityDocumentModel.tenant_id == self.tenant_id)
            .where(PCOSAuthorityDocumentModel.document_code == document_code)
        ).scalar_one_or_none()
        
        if existing:
            return {
                "success": False,
                "error": f"Document with code '{document_code}' already exists",
                "existing_id": str(existing.id)
            }
        
        # Hash file if provided
        document_hash = None
        content_type = None
        file_size_bytes = None
        
        if file_path:
            hash_result = self._hash_file(file_path)
            if hash_result:
                document_hash = hash_result["hash"]
                content_type = hash_result.get("content_type")
                file_size_bytes = hash_result.get("size")
        
        # Create document
        document = PCOSAuthorityDocumentModel(
            tenant_id=self.tenant_id,
            document_code=document_code,
            document_name=document_name,
            document_type=document_type,
            issuer_name=issuer_name,
            issuer_type=issuer_type,
            effective_date=effective_date,
            expiration_date=expiration_date,
            document_hash=document_hash,
            original_file_path=file_path,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            extraction_method=extraction_method,
            extraction_notes=extraction_notes,
            ingested_by=ingested_by,
            status="active"
        )
        
        self.db.add(document)
        self.db.commit()
        
        logger.info(
            "authority_document_registered",
            document_id=str(document.id),
            document_code=document_code,
            issuer=issuer_name
        )
        
        return {
            "success": True,
            "document_id": str(document.id),
            "document_code": document_code,
            "document_name": document_name,
            "document_hash": document_hash,
            "created_at": document.created_at.isoformat()
        }
    
    def list_authority_documents(
        self,
        document_type: Optional[str] = None,
        issuer: Optional[str] = None,
        status: str = "active",
        include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """List authority documents with optional filtering."""
        from .pcos_models import PCOSAuthorityDocumentModel
        from sqlalchemy import select
        
        query = (
            select(PCOSAuthorityDocumentModel)
            .where(PCOSAuthorityDocumentModel.tenant_id == self.tenant_id)
        )
        
        if status:
            query = query.where(PCOSAuthorityDocumentModel.status == status)
        
        if document_type:
            query = query.where(PCOSAuthorityDocumentModel.document_type == document_type)
        
        if issuer:
            query = query.where(PCOSAuthorityDocumentModel.issuer_name.ilike(f"%{issuer}%"))
        
        if not include_expired:
            today = date.today()
            query = query.where(
                (PCOSAuthorityDocumentModel.expiration_date.is_(None)) |
                (PCOSAuthorityDocumentModel.expiration_date >= today)
            )
        
        query = query.order_by(PCOSAuthorityDocumentModel.effective_date.desc())
        
        documents = self.db.execute(query).scalars().all()
        
        return [
            {
                "id": str(doc.id),
                "document_code": doc.document_code,
                "document_name": doc.document_name,
                "document_type": doc.document_type,
                "issuer_name": doc.issuer_name,
                "issuer_type": doc.issuer_type,
                "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
                "expiration_date": doc.expiration_date.isoformat() if doc.expiration_date else None,
                "status": doc.status,
                "has_hash": bool(doc.document_hash),
                "fact_count": len(doc.extracted_facts) if doc.extracted_facts else 0,
                "original_file_path": doc.original_file_path,
                "supersedes_document_id": str(doc.supersedes_document_id) if doc.supersedes_document_id else None
            }
            for doc in documents
        ]

    def export_authority_history(self, authority_code: str) -> Dict[str, Any]:
        """
        Export full lineage history for a given authority code.
        Returns hierarchy of Documents -> Facts with all cryptographic proofs.
        Traverses supersedes chain to include all historical versions.
        """
        from .pcos_models import PCOSAuthorityDocumentModel, PCOSExtractedFactModel
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        
        # 1. Fetch initial documents by code
        initial_docs = self.db.execute(
            select(PCOSAuthorityDocumentModel)
            .where(PCOSAuthorityDocumentModel.tenant_id == self.tenant_id)
            .where(PCOSAuthorityDocumentModel.document_code == authority_code)
            .options(joinedload(PCOSAuthorityDocumentModel.extracted_facts))
        ).scalars().unique().all()
        
        if not initial_docs:
            return {"error": "Authority code not found"}
            
        # 2. Traverse Lineage (Backward via supersedes_document_id)
        # We need a map to avoid duplicates and a queue for traversal
        all_docs_map = {doc.id: doc for doc in initial_docs}
        queue = list(initial_docs)
        
        while queue:
            current = queue.pop(0)
            if current.supersedes_document_id:
                if current.supersedes_document_id not in all_docs_map:
                    # Fetch ancestor
                    ancestor = self.db.execute(
                        select(PCOSAuthorityDocumentModel)
                        .where(PCOSAuthorityDocumentModel.id == current.supersedes_document_id)
                        .options(joinedload(PCOSAuthorityDocumentModel.extracted_facts))
                    ).unique().scalar_one_or_none()
                    
                    if ancestor:
                        all_docs_map[ancestor.id] = ancestor
                        queue.append(ancestor)

        # Convert to list and sort by time
        final_docs = sorted(all_docs_map.values(), key=lambda d: d.created_at, reverse=True)
            
        export_docs = []
        for doc in final_docs:
            facts = []
            for fact in doc.extracted_facts:
                facts.append({
                    "id": str(fact.id),
                    "key": fact.fact_key,
                    "value": self._serialize_fact_value(fact),
                    "condition": fact.validity_conditions,
                    "source_ref": {
                        "page": fact.source_page,
                        "section": fact.source_section
                    },
                    "fact_hash": fact.fact_hash,
                    "is_current": fact.is_current,
                    "superseded_by": None,
                    "version": fact.version,
                    "previous_fact_id": str(fact.previous_fact_id) if fact.previous_fact_id else None
                })
            
            export_docs.append({
                "id": str(doc.id),
                "code": doc.document_code, # Include code as it might differ
                "version": 1, 
                "source_url": doc.original_file_path,
                "ingested_at": doc.ingested_at.isoformat(),
                "document_hash": doc.document_hash,
                "superseded_by": str(doc.supersedes_document_id) if doc.supersedes_document_id else None,
                "facts": facts
            })

        return {
            "authority_code": authority_code,
            "exported_at": datetime.now().isoformat(),
            "documents": export_docs,
            "verification_metadata": {
                "hash_algorithm": "SHA-256",
                "hash_composition": "key|value_type|value|conditions|source_page|source_section"
            }
        }
        
    def list_authority_facts(self, authority_id: UUID) -> List[Dict[str, Any]]:
        """List all extracted facts for a specific authority document."""
        from .pcos_models import PCOSExtractedFactModel
        from sqlalchemy import select
        
        facts = self.db.execute(
            select(PCOSExtractedFactModel)
            .where(PCOSExtractedFactModel.tenant_id == self.tenant_id)
            .where(PCOSExtractedFactModel.authority_document_id == authority_id)
            .order_by(PCOSExtractedFactModel.fact_name)
        ).scalars().all()
        
        return [
            {
                "fact_id": str(fact.id),
                "fact_key": fact.fact_key,
                "fact_name": fact.fact_name,
                "fact_description": fact.fact_description,
                "category": fact.fact_category,
                "value": self._serialize_fact_value(fact),
                "value_type": fact.fact_value_type,
                "confidence": float(fact.extraction_confidence) if fact.extraction_confidence else None,
                "version": fact.version,
                "is_current": fact.is_current,
                "previous_fact_id": str(fact.previous_fact_id) if fact.previous_fact_id else None
            }
            for fact in facts
        ]
    
    # =========================================================================
    # Fact Extraction & Management
    # =========================================================================
    
    def extract_fact(
        self,
        authority_document_id: UUID,
        fact_key: str,
        fact_name: str,
        fact_category: str,
        fact_value: Any,
        fact_value_type: str,
        validity_conditions: Optional[Dict] = None,
        fact_unit: Optional[str] = None,
        fact_description: Optional[str] = None,
        source_page: Optional[int] = None,
        source_section: Optional[str] = None,
        source_quote: Optional[str] = None,
        extraction_confidence: Optional[float] = None,
        extraction_method: str = "manual",
        extracted_by: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Extract and register a fact from an authority document.
        
        Args:
            authority_document_id: Source document ID
            fact_key: Unique key (e.g., 'SAG_MIN_DAY_RATE')
            fact_name: Human-readable name
            fact_category: 'rate', 'threshold', 'deadline', 'requirement'
            fact_value: The actual value
            fact_value_type: 'decimal', 'integer', 'string', 'boolean', 'date', 'json'
            validity_conditions: When this fact applies (budget tier, date range)
            fact_unit: Unit of measure ('USD', 'percent', 'hours')
            source_page: Page in source document
            source_section: Section reference
            source_quote: Verbatim quote from source
            extraction_confidence: 0.0 to 1.0
            extraction_method: 'manual', 'regex', 'nlp'
            extracted_by: User who extracted the fact
            
        Returns:
            Dict with created fact info
        """
        from .pcos_models import PCOSAuthorityDocumentModel, PCOSExtractedFactModel
        from sqlalchemy import select
        
        # Verify authority document exists
        authority = self.db.execute(
            select(PCOSAuthorityDocumentModel)
            .where(PCOSAuthorityDocumentModel.id == authority_document_id)
            .where(PCOSAuthorityDocumentModel.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        
        if not authority:
            return {"success": False, "error": "Authority document not found"}
        
        # Check for existing fact with same key
        existing = self.db.execute(
            select(PCOSExtractedFactModel)
            .where(PCOSExtractedFactModel.tenant_id == self.tenant_id)
            .where(PCOSExtractedFactModel.fact_key == fact_key)
            .where(PCOSExtractedFactModel.is_current == True)
        ).scalar_one_or_none()
        
        # Determine version
        version = 1
        previous_fact_id = None
        
        if existing:
            # Mark existing as not current
            existing.is_current = False
            version = existing.version + 1
            previous_fact_id = existing.id
        
        # Create fact with appropriate value field
        fact = PCOSExtractedFactModel(
            tenant_id=self.tenant_id,
            authority_document_id=authority_document_id,
            fact_key=fact_key,
            fact_name=fact_name,
            fact_category=fact_category,
            fact_description=fact_description,
            fact_value_type=fact_value_type,
            fact_unit=fact_unit,
            validity_conditions=validity_conditions or {},
            version=version,
            previous_fact_id=previous_fact_id,
            is_current=True,
            source_page=source_page,
            source_section=source_section,
            source_quote=source_quote,
            extraction_confidence=Decimal(str(extraction_confidence)) if extraction_confidence else None,
            extraction_method=extraction_method,
            extracted_by=extracted_by
        )
        
        # Set value based on type
        if fact_value_type == "decimal":
            fact.fact_value_decimal = Decimal(str(fact_value))
        elif fact_value_type == "integer":
            fact.fact_value_integer = int(fact_value)
        elif fact_value_type == "string":
            fact.fact_value_string = str(fact_value)
        elif fact_value_type == "boolean":
            fact.fact_value_boolean = bool(fact_value)
        elif fact_value_type == "date":
            fact.fact_value_date = fact_value if isinstance(fact_value, date) else date.fromisoformat(fact_value)
        elif fact_value_type == "json":
            fact.fact_value_json = fact_value
        
        self.db.add(fact)
        self.db.commit()
        
        logger.info(
            "fact_extracted",
            fact_id=str(fact.id),
            fact_key=fact_key,
            version=version,
            authority_code=authority.document_code
        )
        
        return {
            "success": True,
            "fact_id": str(fact.id),
            "fact_key": fact_key,
            "fact_name": fact_name,
            "version": version,
            "is_new": previous_fact_id is None,
            "authority_document": authority.document_code,
            "created_at": fact.created_at.isoformat()
        }
    
    def resolve_fact(
        self,
        fact_key: str,
        context: Optional[Dict] = None,
        as_of_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve the applicable fact for a given context.
        
        Args:
            fact_key: Fact key to look up
            context: Production context (budget, date, union, etc.)
            as_of_date: Date to evaluate validity (defaults to today)
            
        Returns:
            Dict with fact value and provenance, or None if not found
        """
        from .pcos_models import PCOSExtractedFactModel, PCOSAuthorityDocumentModel
        from sqlalchemy import select
        
        context = context or {}
        as_of_date = as_of_date or date.today()
        
        # Get current fact
        fact = self.db.execute(
            select(PCOSExtractedFactModel)
            .where(PCOSExtractedFactModel.tenant_id == self.tenant_id)
            .where(PCOSExtractedFactModel.fact_key == fact_key)
            .where(PCOSExtractedFactModel.is_current == True)
        ).scalar_one_or_none()
        
        if not fact:
            return None
        
        # Check validity conditions
        conditions = fact.validity_conditions or {}
        is_valid = self._check_validity_conditions(conditions, context, as_of_date)
        
        if not is_valid:
            logger.debug("fact_conditions_not_met", fact_key=fact_key, conditions=conditions)
            return None
        
        # Get authority document for provenance
        authority = fact.authority_document
        
        return {
            "fact_id": str(fact.id),
            "fact_key": fact.fact_key,
            "fact_name": fact.fact_name,
            "value": self._serialize_fact_value(fact),
            "value_type": fact.fact_value_type,
            "unit": fact.fact_unit,
            "version": fact.version,
            "validity_conditions": conditions,
            "context_matched": context,
            "provenance": {
                "authority_id": str(authority.id),
                "authority_code": authority.document_code,
                "authority_name": authority.document_name,
                "issuer": authority.issuer_name,
                "document_hash": authority.document_hash,
                "source_page": fact.source_page,
                "source_section": fact.source_section,
                "source_quote": fact.source_quote
            }
        }
    
    # =========================================================================
    # Citation Management
    # =========================================================================
    
    def cite_fact_in_verdict(
        self,
        citing_entity_type: str,
        citing_entity_id: UUID,
        fact_key: str,
        context: Dict,
        citation_type: str,
        input_value: Optional[str] = None,
        comparison_operator: Optional[str] = None,
        evaluation_result: Optional[str] = None,
        citation_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a citation linking a verdict to a fact.
        
        Args:
            citing_entity_type: 'rule_evaluation', 'rate_check', 'compliance_verdict'
            citing_entity_id: ID of the entity using the fact
            fact_key: Fact being cited
            context: Production context that triggered the citation
            citation_type: 'rate_comparison', 'threshold_check', 'deadline_source'
            input_value: What was compared against the fact
            comparison_operator: 'gte', 'lte', 'eq', 'contains'
            evaluation_result: 'pass', 'fail', 'warning'
            citation_notes: Additional notes
            
        Returns:
            Dict with citation info
        """
        from .pcos_models import PCOSExtractedFactModel, PCOSFactCitationModel
        from sqlalchemy import select
        
        # Resolve the fact
        resolved = self.resolve_fact(fact_key, context)
        if not resolved:
            return {"success": False, "error": f"Fact '{fact_key}' not found or not applicable"}
        
        # Get the fact model
        fact = self.db.execute(
            select(PCOSExtractedFactModel)
            .where(PCOSExtractedFactModel.id == UUID(resolved["fact_id"]))
        ).scalar_one()
        
        # Create citation
        citation = PCOSFactCitationModel(
            tenant_id=self.tenant_id,
            citing_entity_type=citing_entity_type,
            citing_entity_id=citing_entity_id,
            extracted_fact_id=fact.id,
            fact_value_used=str(resolved["value"]),
            context_applied=context,
            citation_type=citation_type,
            input_value=input_value,
            comparison_operator=comparison_operator,
            evaluation_result=evaluation_result,
            citation_notes=citation_notes
        )
        
        self.db.add(citation)
        self.db.commit()
        
        logger.info(
            "fact_cited",
            citation_id=str(citation.id),
            fact_key=fact_key,
            entity_type=citing_entity_type,
            entity_id=str(citing_entity_id),
            result=evaluation_result
        )
        
        return {
            "success": True,
            "citation_id": str(citation.id),
            "fact_id": resolved["fact_id"],
            "fact_key": fact_key,
            "fact_value": resolved["value"],
            "provenance": resolved["provenance"],
            "cited_at": citation.cited_at.isoformat()
        }
    
    def get_verdict_lineage(
        self,
        citing_entity_type: str,
        citing_entity_id: UUID
    ) -> Dict[str, Any]:
        """
        Get the full lineage for a verdict/evaluation.
        
        Returns all facts cited by this entity with full provenance
        back to source authority documents.
        """
        from .pcos_models import PCOSFactCitationModel, PCOSExtractedFactModel
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        
        citations = self.db.execute(
            select(PCOSFactCitationModel)
            .where(PCOSFactCitationModel.tenant_id == self.tenant_id)
            .where(PCOSFactCitationModel.citing_entity_type == citing_entity_type)
            .where(PCOSFactCitationModel.citing_entity_id == citing_entity_id)
            .options(joinedload(PCOSFactCitationModel.extracted_fact))
        ).scalars().all()
        
        lineage_items = []
        for citation in citations:
            fact = citation.extracted_fact
            authority = fact.authority_document
            
            lineage_items.append({
                "citation_id": str(citation.id),
                "citation_type": citation.citation_type,
                "evaluation_result": citation.evaluation_result,
                "input_value": citation.input_value,
                "fact_value_used": citation.fact_value_used,
                "comparison_operator": citation.comparison_operator,
                "context_applied": citation.context_applied,
                "fact": {
                    "id": str(fact.id),
                    "key": fact.fact_key,
                    "name": fact.fact_name,
                    "version": fact.version,
                    "source_quote": fact.source_quote
                },
                "authority": {
                    "id": str(authority.id),
                    "code": authority.document_code,
                    "name": authority.document_name,
                    "issuer": authority.issuer_name,
                    "hash": authority.document_hash,
                    "effective_date": authority.effective_date.isoformat() if authority.effective_date else None
                },
                "cited_at": citation.cited_at.isoformat()
            })
        
        return {
            "entity_type": citing_entity_type,
            "entity_id": str(citing_entity_id),
            "total_citations": len(lineage_items),
            "lineage": lineage_items
        }
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _hash_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Calculate SHA-256 hash of a file."""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            sha256_hash = hashlib.sha256()
            with open(path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            # Determine content type
            suffix = path.suffix.lower()
            content_types = {
                ".pdf": "application/pdf",
                ".doc": "application/msword",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".txt": "text/plain",
                ".html": "text/html",
            }
            
            return {
                "hash": sha256_hash.hexdigest(),
                "content_type": content_types.get(suffix, "application/octet-stream"),
                "size": path.stat().st_size
            }
        except Exception as e:
            logger.warning("file_hash_failed", path=file_path, error=str(e))
            return None
    
    def _check_validity_conditions(
        self,
        conditions: Dict,
        context: Dict,
        as_of_date: date
    ) -> bool:
        """Check if conditions are met by the context."""
        # Check budget range
        if "budget_min" in conditions:
            ctx_budget = context.get("budget", 0)
            if ctx_budget < conditions["budget_min"]:
                return False
        
        if "budget_max" in conditions:
            ctx_budget = context.get("budget", float("inf"))
            if ctx_budget > conditions["budget_max"]:
                return False
        
        # Check date constraints
        if "date_after" in conditions:
            threshold = date.fromisoformat(conditions["date_after"])
            if as_of_date < threshold:
                return False
        
        if "date_before" in conditions:
            threshold = date.fromisoformat(conditions["date_before"])
            if as_of_date > threshold:
                return False
        
        # Check union
        if "union" in conditions:
            if context.get("union") != conditions["union"]:
                return False
        
        # Check project type
        if "project_type" in conditions:
            if context.get("project_type") != conditions["project_type"]:
                return False
        
        return True
    
    def _serialize_fact_value(self, fact) -> Any:
        """Serialize fact value for JSON response."""
        value = fact.get_value()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, date):
            return value.isoformat()
        return value
