"""Storage manager for documents."""

from pathlib import Path
from typing import Optional, Tuple

from ..models import Document
from ..utils import hash_content, generate_document_id


class StorageManager:
    """
    Manages document storage to filesystem or S3.
    
    Handles deduplication via content hashing.
    """
    
    def __init__(self, base_path: Path):
        """
        Initialize storage manager.
        
        Args:
            base_path: Base directory for document storage
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories by vertical
        self.documents_dir = base_path / "documents"
        self.documents_dir.mkdir(exist_ok=True)
    
    def store_document(
        self,
        content: bytes,
        vertical: str,
        document_id: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Store document content.
        
        Args:
            content: Raw document bytes
            vertical: Regulatory vertical
            document_id: Optional document ID (generated if not provided)
            
        Returns:
            Tuple of (document_id, storage_key, content_sha256)
        """
        # Hash content
        content_sha256, content_sha512 = hash_content(content)
        
        # Generate document ID if not provided
        if not document_id:
            document_id = generate_document_id(content_sha256)
        
        # Create storage path: documents/{vertical}/{first_2_chars}/{doc_id}
        vertical_dir = self.documents_dir / vertical
        vertical_dir.mkdir(exist_ok=True)
        
        prefix_dir = vertical_dir / content_sha256[:2]
        prefix_dir.mkdir(exist_ok=True)
        
        file_path = prefix_dir / f"{document_id}.bin"
        storage_key = str(file_path.relative_to(self.base_path))
        
        # Write content
        file_path.write_bytes(content)
        
        return document_id, storage_key, content_sha256
    
    def retrieve_document(self, storage_key: str) -> bytes:
        """
        Retrieve document content.
        
        Args:
            storage_key: Storage key from store_document
            
        Returns:
            Document content bytes
        """
        file_path = self.base_path / storage_key
        return file_path.read_bytes()
    
    def document_exists(self, content_sha256: str, vertical: str) -> bool:
        """
        Check if document already exists (deduplication).
        
        Args:
            content_sha256: SHA-256 hash of content
            vertical: Regulatory vertical
            
        Returns:
            True if document exists, False otherwise
        """
        prefix_dir = self.documents_dir / vertical / content_sha256[:2]
        if not prefix_dir.exists():
            return False
        
        doc_id = generate_document_id(content_sha256)
        file_path = prefix_dir / f"{doc_id}.bin"
        return file_path.exists()
