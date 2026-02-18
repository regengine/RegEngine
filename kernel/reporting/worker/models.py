
from sqlalchemy import Column, String, Date, DateTime, BigInteger, Text, ForeignKey, Integer, Boolean, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class AuthorityDocument(Base):
    __tablename__ = "pcos_authority_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    
    document_code = Column(String(100), nullable=False)
    document_name = Column(String(255), nullable=False)
    document_type = Column(String(50), nullable=False)
    
    issuer_name = Column(String(255), nullable=False)
    issuer_type = Column(String(50))
    
    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date)
    supersedes_document_id = Column(UUID(as_uuid=True), ForeignKey("pcos_authority_documents.id"))
    
    document_hash = Column(String(64))
    original_file_path = Column(Text)
    content_type = Column(String(100))
    file_size_bytes = Column(BigInteger)
    
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class ExtractedFact(Base):
    __tablename__ = "pcos_extracted_facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    
    authority_document_id = Column(UUID(as_uuid=True), ForeignKey("pcos_authority_documents.id"), nullable=False)
    
    fact_key = Column(String(100), nullable=False)
    fact_category = Column(String(50), nullable=False)
    fact_name = Column(String(255), nullable=False)
    fact_description = Column(Text)
    
    # Value fields
    fact_value_type = Column(String(20), nullable=False)
    fact_value_decimal = Column(Numeric(15, 4))
    fact_value_integer = Column(Integer)
    fact_value_string = Column(Text)
    fact_value_boolean = Column(Boolean)
    fact_value_date = Column(Date)
    fact_value_json = Column(JSON)
    fact_unit = Column(String(50))
    
    validity_conditions = Column(JSON, nullable=False, default=dict)
    
    fact_hash = Column(String(64))

    version = Column(Integer, nullable=False, default=1)
    previous_fact_id = Column(UUID(as_uuid=True))
    is_current = Column(Boolean, nullable=False, default=True)
    
    source_page = Column(Integer)
    source_section = Column(String(255))
    source_quote = Column(Text)
    
    extraction_confidence = Column(Numeric(3, 2))
    extraction_method = Column(String(50))
    extraction_notes = Column(Text)
    
    extracted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    extracted_by = Column(UUID(as_uuid=True))
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(UUID(as_uuid=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

