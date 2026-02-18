"""Provenance replay / auditor tooling for deterministic verification."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID, uuid4

from services.graph.app.neo4j_utils import Neo4jClient
from services.nlp.app.extractors import EXTRACTOR_REGISTRY, get_extractor
from shared.schemas import ExtractionPayload

logger = logging.getLogger(__name__)


class VersionMismatchError(Exception):
    """Raised when replay uses a different model version than the stored record."""


EXTRACTOR_NAME_TO_FRAMEWORK = {
    "NYDFSExtractor": "US-NY-500",
    "DORAExtractor": "DORA",
    "SECSCIExtractor": "US-SEC-SCI",
}


class ProvenanceVerifier:
    """Auditor helper that replays extractions against stored graph data."""

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self._preferred_database = Neo4jClient.get_tenant_database_name(tenant_id)
        try:
            self._client = Neo4jClient(database=self._preferred_database)
        except Exception as exc:  # pragma: no cover - depends on Neo4j edition
            logger.warning(
                "tenant_database_unavailable_falling_back tenant=%s error=%s",
                tenant_id,
                exc,
            )
            self._client = Neo4jClient()
            self._preferred_database = Neo4jClient.get_global_database_name()

    @contextmanager
    def _session(self, client: Optional[Neo4jClient] = None) -> Iterable:
        neo_client = client or self._client
        session = neo_client.session()
        try:
            yield session
        finally:
            session.close()

    def _run_query(self, query: str, **params) -> Optional[Dict[str, Any]]:
        try:
            with self._session() as session:
                result = session.run(query, **params).single()
                return dict(result) if result else None
        except Exception as exc:
            if self._preferred_database == Neo4jClient.get_global_database_name():
                raise
            logger.warning(
                "tenant_query_failed_falling_back tenant=%s error=%s",
                self.tenant_id,
                exc,
            )
            fallback = Neo4jClient()
            try:
                with self._session(fallback) as session:
                    result = session.run(query, **params).single()
                    return dict(result) if result else None
            finally:
                fallback.close()

    def get_stored_record(self, provision_hash: str) -> Tuple[str, Optional[str], str]:
        """Fetch immutable record for a provision hash from Neo4j."""

        query = """
        MATCH (p:Provision {hash: $hash})
        RETURN p.hash AS content_hash,
               p.extraction AS extraction,
               p.provenance AS provenance,
               p.text_clean AS text_clean
        """
        record = self._run_query(query, hash=provision_hash)
        if not record:
            raise LookupError(f"No provision found for hash: {provision_hash}")

        extraction = record.get("extraction") or {}
        if isinstance(extraction, str):
            try:
                extraction = json.loads(extraction)
            except json.JSONDecodeError:
                extraction = {}
        attributes = extraction.get("attributes") or {}
        metadata_framework = (
            attributes.get("framework_code")
            or attributes.get("framework")
            or extraction.get("jurisdiction")
        )
        extractor_hint = attributes.get("extractor")

        return (
            record.get("content_hash") or provision_hash,
            self._deduce_framework(metadata_framework, extractor_hint),
            attributes.get("model_version", "v1"),
        )

    def _deduce_framework(self, framework_hint: Optional[str], extractor_hint: Optional[str]) -> Optional[str]:
        if framework_hint in EXTRACTOR_REGISTRY:
            return framework_hint
        if extractor_hint and extractor_hint in EXTRACTOR_NAME_TO_FRAMEWORK:
            return EXTRACTOR_NAME_TO_FRAMEWORK[extractor_hint]
        return framework_hint

    def verify(self, raw_text: str, correlation_id: str, framework_override: Optional[str] = None) -> bool:
        """Re-run extraction pipeline and compare hashes against stored record."""

        try:
            stored_hash, stored_framework, stored_version = self.get_stored_record(correlation_id)
        except LookupError as exc:
            logger.error(str(exc))
            return False

        framework = framework_override or stored_framework
        if not framework:
            logger.error("Unable to determine extractor framework for replay")
            return False

        try:
            extractor = get_extractor(framework)
        except ValueError as exc:
            logger.error("extractor_lookup_failed framework=%s error=%s", framework, exc)
            return False

        current_version = getattr(extractor, "VERSION", "v1")
        if current_version != stored_version:
            raise VersionMismatchError(
                f"Stored version {stored_version} != current version {current_version}"
            )

        try:
            replay_payloads = self._run_extractor(extractor, framework, raw_text)
        except Exception as exc:  # pragma: no cover - extractor dependent
            logger.error("replay_extraction_failed framework=%s error=%s", framework, exc)
            return False

        replay_hashes = self._hash_payloads(replay_payloads)
        if stored_hash in replay_hashes:
            logger.info("provenance_verified hash=%s framework=%s", stored_hash, framework)
            return True

        logger.error(
            "provenance_mismatch hash=%s framework=%s replay_hashes=%s",
            stored_hash,
            framework,
            list(replay_hashes)[:5],
        )
        return False

    def _run_extractor(self, extractor, framework: str, raw_text: str) -> List[Any]:
        if hasattr(extractor, "extract_obligations"):
            document_id = uuid4()
            return extractor.extract_obligations(raw_text, document_id, self.tenant_id)
        if hasattr(extractor, "extract"):
            jurisdiction = framework if framework != "GENERIC" else "US"
            return extractor.extract(raw_text, jurisdiction)
        raise RuntimeError(f"Extractor for {framework} does not expose a supported interface")

    def _hash_payloads(self, payloads: List[Any]) -> List[str]:
        hashes: List[str] = []
        for payload in payloads:
            text = self._extract_text(payload)
            if not text:
                continue
            normalized = text.strip()
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            hashes.append(digest)
            hashes.append(digest[:16])  # include truncated variant used in legacy schemas
        return hashes

    def _extract_text(self, payload: Any) -> str:
        if hasattr(payload, "provision_text"):
            return getattr(payload, "provision_text")
        if isinstance(payload, ExtractionPayload):  # pragma: no cover - defensive
            return payload.source_text
        if hasattr(payload, "source_text"):
            return getattr(payload, "source_text")
        if isinstance(payload, dict):
            return payload.get("provision_text") or payload.get("source_text") or ""
        return str(payload)