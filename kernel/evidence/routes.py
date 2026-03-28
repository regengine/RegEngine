"""
Evidence Service - FastAPI Routes
==================================
REST API endpoints for evidence verification.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
import logging

from shared.auth import APIKey, require_api_key

from .envelope import (
    EvidenceEnvelopeV3,
    VerificationRequest,
    VerificationResult,
    ChainStats
)
from .verify import EvidenceVerifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/evidence", tags=["evidence"])

# In-memory evidence store (in production, this would be a database/graph)
envelope_store: Dict[str, EvidenceEnvelopeV3] = {}
verifier = EvidenceVerifier(envelope_store=envelope_store)


@router.post("/verify", response_model=VerificationResult)
async def verify_evidence(request: VerificationRequest, api_key: APIKey = Depends(require_api_key)):
    """
    Verify evidence envelope integrity.
    
    **Checks Performed**:
    1. Payload hash matches evidence content (tamper detection)
    2. Current hash correctly computed
    3. Previous hash links to valid predecessor (chain continuity)
    4. Merkle proof validates (batch integrity)
    
    **Returns**:
    - Verification result with detailed checks
    - Tamper detection flag
    - Chain length from envelope to root
    """
    try:
        # Look up envelope
        if request.envelope_id not in envelope_store:
            raise HTTPException(
                status_code=404,
                detail=f"Envelope {request.envelope_id} not found"
            )
        
        envelope = envelope_store[request.envelope_id]
        
        # Verify envelope
        result = verifier.verify_envelope(envelope)
        
        return result
        
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.get("/chain/{envelope_id}", response_model=VerificationResult)
async def verify_chain(envelope_id: str, api_key: APIKey = Depends(require_api_key)):
    """
    Verify entire evidence chain from envelope to root.
    
    Recursively validates all envelopes in chain.
    
    **Returns**:
    - Verification result for head envelope
    - Chain length (number of envelopes from head to root)
    """
    try:
        result = verifier.verify_chain(envelope_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Chain verification failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chain verification failed: {str(e)}")


@router.post("/envelopes", response_model=EvidenceEnvelopeV3)
async def create_envelope(envelope: EvidenceEnvelopeV3, api_key: APIKey = Depends(require_api_key)):
    """
    Create and store a new evidence envelope.
    
    **Note**: This is a temporary endpoint for testing.
    In production, envelopes are created automatically
    when decisions/events are recorded.
    """
    try:
        # Store envelope
        envelope_store[envelope.envelope_id] = envelope
        
        logger.info(f"Created envelope {envelope.envelope_id}")
        
        return envelope
        
    except Exception as e:
        logger.error(f"Envelope creation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Envelope creation failed: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "evidence",
        "envelopes_stored": len(envelope_store)
    }
