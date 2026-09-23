"""Inbound email ingestion slice.

Receives Postmark's inbound-parse webhook, resolves a tenant from the
recipient address, runs any CSV attachment through the existing
``app.csv_templates.ingest_csv`` path, and records one audit row per
email (see ``DESIGN_email-ingestion.md`` at the repo root).
"""
