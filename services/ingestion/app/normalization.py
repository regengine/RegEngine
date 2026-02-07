"""Utilities for normalizing regulatory documents."""

from __future__ import annotations

import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Optional

from dateutil import parser

from .models import PositionMapEntry, TextExtractionMetadata

logger = logging.getLogger("ingestion.normalization")


def normalize_document(
    raw_payload: dict[str, Any] | None,
    raw_bytes: bytes,
    source_url: str,
    content_type: Optional[str],
) -> Tuple[dict[str, Any], str, str]:
    """Normalize a regulatory document.

    Returns the normalized payload, document identifier, and content hash.
    """

    extracted_text, extraction_meta, position_map = _extract_text(
        raw_payload=raw_payload,
        raw_bytes=raw_bytes,
        content_type=content_type,
    )

    if raw_payload is None:
        raw_payload = {}

    title = raw_payload.get("title") or raw_payload.get("headline")
    jurisdiction = raw_payload.get("jurisdiction") or raw_payload.get("agency")
    retrieved_at = _parse_datetime(raw_payload.get("publication_date")) or datetime.now(
        timezone.utc
    )

    document_id = raw_payload.get("document_id") or _derive_document_id(
        source_url, extracted_text
    )

    normalized = {
        "document_id": document_id,
        "source_url": source_url,
        "source_system": raw_payload.get("source_system", "unknown"),
        "retrieved_at": retrieved_at,
        "title": title,
        "jurisdiction": jurisdiction,
        "text": extracted_text,
        "position_map": position_map,
        "text_extraction": extraction_meta,
        "content_type": content_type,
    }

    content_sha256 = _content_hash(normalized)
    normalized["content_sha256"] = content_sha256

    return normalized, document_id, content_sha256


def _derive_document_id(source_url: str, text: str) -> str:
    seed = f"{source_url}|{text[:4096]}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _content_hash(normalized_payload: Dict[str, Any]) -> str:
    serializable = {
        key: _serialize_datetime(value)
        for key, value in normalized_payload.items()
        if key != "content_sha256"
    }
    payload_bytes = json.dumps(serializable, sort_keys=True, default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(payload_bytes).hexdigest()


def _serialize_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, list):
        return [_serialize_datetime(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_datetime(v) for k, v in value.items()}
    return value


def _extract_text(
    raw_payload: dict[str, Any] | None,
    raw_bytes: bytes,
    content_type: Optional[str],
) -> Tuple[str, TextExtractionMetadata | None, List[PositionMapEntry] | None]:
    """Extract text from document using format-specific extractors."""
    
    # Import format extractors
    from .format_extractors import (
        extract_from_html,
        extract_from_xml,
        extract_from_csv,
        extract_from_excel,
        extract_from_docx,
        extract_from_edi,
        detect_format,
        is_edi_content,
    )
    
    # First try to extract from JSON payload if available
    if raw_payload:
        candidate_text = _extract_text_from_payload(raw_payload)
        if candidate_text:
            position_map = [
                PositionMapEntry(
                    page=1,
                    char_start=0,
                    char_end=len(candidate_text),
                    source_start=0,
                    source_end=len(candidate_text),
                )
            ]
            return (
                candidate_text,
                TextExtractionMetadata(
                    engine="payload", confidence_mean=1.0, confidence_std=0.0
                ),
                position_map,
            )

    # Detect format and use appropriate extractor
    detected_format = detect_format(content_type, raw_bytes)
    ct_lower = (content_type or "").lower()
    
    # HTML extraction
    if detected_format == "html" or "html" in ct_lower:
        return extract_from_html(raw_bytes)
    
    # XML extraction (but not HTML)
    if detected_format == "xml" or ("xml" in ct_lower and "html" not in ct_lower):
        return extract_from_xml(raw_bytes)
    
    # CSV extraction
    if detected_format == "csv" or "csv" in ct_lower or "comma-separated" in ct_lower:
        return extract_from_csv(raw_bytes)
    
    # Excel extraction
    if detected_format == "excel" or any(x in ct_lower for x in ["spreadsheet", "excel", "xlsx", "xls"]):
        return extract_from_excel(raw_bytes)
    
    # Word DOCX extraction
    if detected_format == "docx" or any(x in ct_lower for x in ["wordprocessing", "msword", "docx"]):
        return extract_from_docx(raw_bytes)
    
    # EDI extraction
    if detected_format == "edi" or "edi" in ct_lower or is_edi_content(raw_bytes):
        return extract_from_edi(raw_bytes)
    
    # PDF extraction (existing logic)
    if detected_format == "pdf" or "pdf" in ct_lower:
        text, meta, position_map = _extract_from_pdf(raw_bytes)
        return text, meta, position_map

    # Fallback: raw bytes as text
    if raw_bytes:
        text = raw_bytes.decode("utf-8", errors="ignore")
        position_map = [
            PositionMapEntry(
                page=1,
                char_start=0,
                char_end=len(text),
                source_start=0,
                source_end=len(raw_bytes),
            )
        ]
        return (
            text,
            TextExtractionMetadata(
                engine="bytes", confidence_mean=0.5, confidence_std=0.3
            ),
            position_map,
        )

    return (
        "",
        TextExtractionMetadata(
            engine="unknown", confidence_mean=0.0, confidence_std=1.0
        ),
        [],
    )




def _extract_text_from_payload(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("body"),
        payload.get("text"),
        payload.get("content"),
        payload.get("abstract"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _extract_from_pdf(
    raw_bytes: bytes,
) -> Tuple[str, TextExtractionMetadata, List[PositionMapEntry]]:
    text = ""
    position_map: List[PositionMapEntry] = []
    try:
        from pdfminer.high_level import extract_text
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("pdfminer_missing")
    else:
        try:
            text = extract_text(io.BytesIO(raw_bytes)) or ""
        except Exception as exc:  # pragma: no cover - library dependent
            logger.warning("pdfminer_failed", exc_info=exc)
    if text.strip():
        position_map = [
            PositionMapEntry(
                page=1,
                char_start=0,
                char_end=len(text),
                source_start=0,
                source_end=len(raw_bytes),
            )
        ]
        return (
            text,
            TextExtractionMetadata(
                engine="pdfminer", confidence_mean=0.9, confidence_std=0.05
            ),
            position_map,
        )

    # Fallback to Tesseract OCR
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("tesseract_missing")
        return (
            "",
            TextExtractionMetadata(
                engine="unavailable", confidence_mean=0.0, confidence_std=1.0
            ),
            [],
        )

    images = []
    try:
        images = convert_from_bytes(raw_bytes)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("pdf_rasterization_failed", exc_info=exc)
        return (
            "",
            TextExtractionMetadata(
                engine="tesseract", confidence_mean=0.0, confidence_std=1.0
            ),
            [],
        )

    page_texts: List[str] = []
    confidences: List[float] = []
    cursor = 0
    for page_num, image in enumerate(images, start=1):
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.warning("tesseract_failed", exc_info=exc)
            continue
        words: List[str] = []
        confs: List[float] = []
        for word, conf in zip(data.get("text", []), data.get("conf", [])):
            if word.strip():
                words.append(word.strip())
                try:
                    conf_val = float(conf)
                except ValueError:
                    conf_val = 0.0
                if conf_val >= 0:
                    confs.append(conf_val / 100.0)
        page_text = " ".join(words)
        page_texts.append(page_text)
        confidences.extend(confs)
        position_map.append(
            PositionMapEntry(
                page=page_num,
                char_start=cursor,
                char_end=cursor + len(page_text),
                source_start=None,
                source_end=None,
            )
        )
        cursor += len(page_text) + 1  # account for newline spacing

    final_text = "\n".join(page_texts)
    if confidences:
        mean_conf = sum(confidences) / len(confidences)
        variance = sum((c - mean_conf) ** 2 for c in confidences) / len(confidences)
    else:
        mean_conf = 0.5
        variance = 0.25
    return (
        final_text,
        TextExtractionMetadata(
            engine="tesseract",
            confidence_mean=round(mean_conf, 4),
            confidence_std=round(variance**0.5, 4),
        ),
        position_map,
    )


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = parser.isoparse(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
