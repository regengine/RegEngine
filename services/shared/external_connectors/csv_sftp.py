"""CSV / SFTP generic connector.

This connector covers the majority of ERP integration needs:
  - SAP S/4HANA exports traceability data as CSV/EDI
  - Oracle NetSuite exports to CSV/SFTP
  - Fishbowl Inventory generates CSV reports
  - QuickBooks exports inventory as CSV

Instead of building N separate ERP connectors (each requiring
vendor partnerships), this connector accepts CSV files via:
  1. Direct upload (REST API)
  2. SFTP polling (scheduled)
  3. S3/blob drop (event-driven)

Column mapping is configurable per tenant — they tell us which
CSV column maps to which FSMA 204 field.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import (
    AuthType,
    ConnectorConfig,
    ConnectionStatus,
    IntegrationConnector,
    NormalizedCTEEvent,
)

logger = logging.getLogger("connector-csv-sftp")

# Default column mapping: CSV header → RegEngine field
# Tenants can override this per-integration
DEFAULT_COLUMN_MAP: Dict[str, str] = {
    # Common ERP column names → RegEngine fields
    "lot_code": "traceability_lot_code",
    "lot_number": "traceability_lot_code",
    "lot": "traceability_lot_code",
    "tlc": "traceability_lot_code",
    "traceability_lot_code": "traceability_lot_code",
    "batch_number": "traceability_lot_code",
    "batch": "traceability_lot_code",
    "product": "product_description",
    "product_name": "product_description",
    "product_description": "product_description",
    "item_name": "product_description",
    "item_description": "product_description",
    "description": "product_description",
    "commodity": "product_description",
    "qty": "quantity",
    "quantity": "quantity",
    "amount": "quantity",
    "count": "quantity",
    "uom": "unit_of_measure",
    "unit": "unit_of_measure",
    "unit_of_measure": "unit_of_measure",
    "units": "unit_of_measure",
    "date": "timestamp",
    "event_date": "timestamp",
    "timestamp": "timestamp",
    "datetime": "timestamp",
    "ship_date": "timestamp",
    "receive_date": "timestamp",
    "harvest_date": "timestamp",
    "gln": "location_gln",
    "location_gln": "location_gln",
    "global_location_number": "location_gln",
    "location": "location_name",
    "location_name": "location_name",
    "facility": "location_name",
    "warehouse": "location_name",
    "site": "location_name",
    "event_type": "cte_type",
    "cte_type": "cte_type",
    "cte": "cte_type",
    "type": "cte_type",
}

# CTE type aliases from ERP systems
CTE_TYPE_ALIASES: Dict[str, str] = {
    "ship": "shipping",
    "shipped": "shipping",
    "dispatch": "shipping",
    "outbound": "shipping",
    "receive": "receiving",
    "received": "receiving",
    "receipt": "receiving",
    "inbound": "receiving",
    "cool": "cooling",
    "cooled": "cooling",
    "cold_storage": "cooling",
    "harvest": "harvesting",
    "harvested": "harvesting",
    "picked": "harvesting",
    "pack": "initial_packing",
    "packed": "initial_packing",
    "packing": "initial_packing",
    "transform": "transformation",
    "transformed": "transformation",
    "processing": "transformation",
    "processed": "transformation",
    "manufacture": "transformation",
    "landing": "first_land_based_receiving",
}


class CSVSFTPConnector(IntegrationConnector):
    """Generic CSV/SFTP connector for ERP integration.

    Accepts CSV data from any source (upload, SFTP, S3) and normalizes
    rows into FSMA 204 CTE events using configurable column mapping.

    This single connector covers SAP, NetSuite, Fishbowl, QuickBooks,
    and any other system that can export CSV.
    """

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        # Tenant-specific column mapping overrides
        self._column_map: Dict[str, str] = {
            **DEFAULT_COLUMN_MAP,
            **config.extra.get("column_map", {}),
        }
        # Default CTE type when not specified in CSV
        self._default_cte_type: str = config.extra.get(
            "default_cte_type", "receiving"
        )
        # SFTP config
        self._sftp_host: str = config.extra.get("sftp_host", "")
        self._sftp_port: int = config.extra.get("sftp_port", 22)
        self._sftp_username: str = config.extra.get("sftp_username", "")
        self._sftp_path: str = config.extra.get("sftp_path", "/outbound/")
        # Source identifier for audit trail
        self._source_system: str = config.extra.get("source_system", "csv_upload")

    async def test_connection(self) -> bool:
        """Test connection.

        For direct upload: always True (stateless).
        For SFTP: test SSH connection.
        For S3: test bucket access.
        """
        if self._sftp_host:
            return await self._test_sftp_connection()
        # Direct upload is always available
        self._status = ConnectionStatus.CONNECTED
        return True

    async def _test_sftp_connection(self) -> bool:
        """Test SFTP connection (requires asyncssh)."""
        try:
            import asyncssh
            async with asyncssh.connect(
                self._sftp_host,
                port=self._sftp_port,
                username=self._sftp_username,
                password=self.config.api_key,
                known_hosts=None,
            ) as conn:
                async with conn.start_sftp_client() as sftp:
                    await sftp.listdir(self._sftp_path)
            self._status = ConnectionStatus.CONNECTED
            return True
        except ImportError:
            logger.warning("asyncssh not installed — SFTP unavailable")
            self._status = ConnectionStatus.ERROR
            return False
        except Exception as exc:
            logger.error("sftp_connection_failed error=%s", str(exc))
            self._status = ConnectionStatus.ERROR
            return False

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        """Fetch events from SFTP directory.

        For direct upload, use parse_csv() instead.
        """
        if not self._sftp_host:
            # Direct upload mode — no fetch, data comes via parse_csv()
            return [], None

        try:
            import asyncssh
            events: List[NormalizedCTEEvent] = []

            async with asyncssh.connect(
                self._sftp_host,
                port=self._sftp_port,
                username=self._sftp_username,
                password=self.config.api_key,
                known_hosts=None,
            ) as conn:
                async with conn.start_sftp_client() as sftp:
                    files = await sftp.listdir(self._sftp_path)
                    csv_files = sorted(
                        [f for f in files if f.endswith(".csv")],
                    )

                    for filename in csv_files[:limit]:
                        filepath = f"{self._sftp_path}/{filename}"
                        content = await sftp.open(filepath, "r")
                        text = await content.read()
                        await content.close()

                        batch = self.parse_csv(text, source_file=filename)
                        events.extend(batch)

                        # Move processed file to /processed/
                        try:
                            await sftp.rename(
                                filepath,
                                f"{self._sftp_path}/processed/{filename}",
                            )
                        except Exception:
                            pass  # best-effort move

            return events[:limit], None

        except ImportError:
            return [], None
        except Exception as exc:
            logger.error("sftp_fetch_failed error=%s", str(exc))
            return [], None

    def parse_csv(
        self,
        csv_content: str,
        source_file: str = "upload",
        encoding: str = "utf-8",
    ) -> List[NormalizedCTEEvent]:
        """Parse CSV content into CTE events.

        This is the main entry point for direct upload mode.
        Handles:
          - Auto-detecting column mapping
          - Normalizing values (dates, units, CTE types)
          - Skipping invalid rows with error logging
        """
        events: List[NormalizedCTEEvent] = []
        reader = csv.DictReader(io.StringIO(csv_content))

        if not reader.fieldnames:
            logger.warning("csv_empty_headers source=%s", source_file)
            return events

        # Build mapping: CSV column → RegEngine field
        col_mapping = self._resolve_column_mapping(reader.fieldnames)

        for row_num, row in enumerate(reader, start=2):
            try:
                event = self._row_to_event(row, col_mapping, source_file, row_num)
                if event:
                    events.append(event)
            except Exception as exc:
                logger.warning(
                    "csv_row_failed source=%s row=%d error=%s",
                    source_file, row_num, str(exc),
                )

        logger.info(
            "csv_parsed source=%s rows=%d events=%d",
            source_file, row_num if reader.line_num else 0, len(events),
        )
        return events

    def _resolve_column_mapping(
        self, fieldnames: List[str]
    ) -> Dict[str, str]:
        """Map CSV headers to RegEngine fields using fuzzy matching."""
        mapping: Dict[str, str] = {}
        for col in fieldnames:
            normalized = col.strip().lower().replace(" ", "_").replace("-", "_")
            if normalized in self._column_map:
                mapping[col] = self._column_map[normalized]
        return mapping

    def _row_to_event(
        self,
        row: Dict[str, str],
        col_mapping: Dict[str, str],
        source_file: str,
        row_num: int,
    ) -> Optional[NormalizedCTEEvent]:
        """Convert a single CSV row into a CTE event."""
        # Extract mapped fields
        mapped: Dict[str, str] = {}
        extra_kdes: Dict[str, Any] = {}

        for csv_col, value in row.items():
            if not value or not value.strip():
                continue
            value = value.strip()

            if csv_col in col_mapping:
                mapped[col_mapping[csv_col]] = value
            else:
                # Store unmapped columns as KDEs
                safe_key = csv_col.strip().lower().replace(" ", "_")[:50]
                if safe_key:
                    extra_kdes[safe_key] = value

        # Require at minimum a lot code
        tlc = mapped.get("traceability_lot_code")
        if not tlc:
            return None

        # CTE type
        raw_cte = mapped.get("cte_type", self._default_cte_type)
        cte_type = CTE_TYPE_ALIASES.get(raw_cte.lower(), raw_cte.lower())

        # Quantity
        quantity = 1.0
        if mapped.get("quantity"):
            try:
                quantity = float(mapped["quantity"].replace(",", ""))
            except ValueError:
                pass

        # Timestamp
        timestamp = mapped.get("timestamp")
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Add source metadata to KDEs
        extra_kdes["csv_source_file"] = source_file
        extra_kdes["csv_row_number"] = row_num
        extra_kdes["csv_source_system"] = self._source_system

        return NormalizedCTEEvent(
            cte_type=cte_type,
            traceability_lot_code=tlc,
            product_description=mapped.get("product_description", f"CSV Row {row_num}"),
            quantity=quantity,
            unit_of_measure=mapped.get("unit_of_measure", "units"),
            timestamp=timestamp,
            location_gln=mapped.get("location_gln"),
            location_name=mapped.get("location_name"),
            kdes=extra_kdes,
            source_event_id=f"{source_file}:row-{row_num}",
        )

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        """Normalize a pre-parsed dict (for API compatibility)."""
        return NormalizedCTEEvent(
            cte_type=raw_event.get("cte_type", self._default_cte_type),
            traceability_lot_code=raw_event.get("traceability_lot_code", ""),
            product_description=raw_event.get("product_description", ""),
            quantity=float(raw_event.get("quantity", 1)),
            unit_of_measure=raw_event.get("unit_of_measure", "units"),
            timestamp=raw_event.get("timestamp", datetime.now(timezone.utc).isoformat()),
            location_gln=raw_event.get("location_gln"),
            location_name=raw_event.get("location_name"),
            kdes=raw_event.get("kdes", {}),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {
            "id": "csv_sftp",
            "name": "CSV / SFTP Import",
            "category": "developer",
            "description": (
                "Import traceability data from any ERP or warehouse system "
                "via CSV file upload, SFTP polling, or S3 drop. Configurable "
                "column mapping supports SAP, NetSuite, Fishbowl, QuickBooks, "
                "and any system that exports CSV."
            ),
            "supported_cte_types": [
                "receiving", "shipping", "cooling", "harvesting",
                "initial_packing", "transformation", "first_land_based_receiving",
            ],
            "auth_type": AuthType.API_KEY.value,
            "features": [
                "Direct CSV upload via API",
                "SFTP directory polling",
                "Auto column mapping",
                "Custom column mapping per tenant",
                "SAP/NetSuite/Fishbowl/QuickBooks compatible",
                "Batch processing (500+ rows)",
            ],
        }
