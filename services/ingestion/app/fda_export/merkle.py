"""
Merkle tree root calculation and inclusion proofs.

Extracted from fda_export_router.py — pure structural refactor.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger("fda-export")


async def get_merkle_root_handler(tenant_id: str) -> dict:
    """Return the current Merkle root for a tenant's hash chain.

    This is the core logic for the /export/merkle-root endpoint.
    """
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        result = persistence.verify_chain_merkle(tenant_id)

        return {
            "tenant_id": tenant_id,
            "valid": result.valid,
            "merkle_root": result.merkle_root,
            "chain_length": result.chain_length,
            "tree_depth": result.tree_depth,
            "errors": result.errors,
            "checked_at": result.checked_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "merkle_root_failed",
            extra={"error": str(e), "tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Merkle root computation failed. Check server logs.",
        )
    finally:
        if db_session:
            db_session.close()


async def get_merkle_proof_handler(tenant_id: str, event_id: str) -> dict:
    """Return a Merkle inclusion proof for a specific event.

    This is the core logic for the /export/merkle-proof endpoint.
    """
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)

        proof_data = persistence.get_merkle_proof(tenant_id, event_id)

        if proof_data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Event '{event_id}' not found in hash chain for tenant '{tenant_id}'",
            )

        return {
            "tenant_id": tenant_id,
            **proof_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "merkle_proof_failed",
            extra={"error": str(e), "tenant_id": tenant_id, "event_id": event_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Merkle proof generation failed. Check server logs.",
        )
    finally:
        if db_session:
            db_session.close()
