/**
 * Step 8: FDA 24-Hour Export (LIVE)
 * Calls apiClient.getSupplierFDAExportPreview and apiClient.downloadSupplierFDARecords
 *
 * KEY FIX: Shows FDA_SAMPLE_ROWS in demo mode instead of an error state.
 * Unauthenticated users see realistic sample data with a clear "Sample data" label.
 */
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { ACCENT, GRAY, GRAY_LIGHT, BORDER, ERROR, BLUE_LIGHT, BLUE } from "../shared/styles";
import { Card, SectionTitle, InfoCallout } from "../shared/components";
import { VIEWS, FDA_SAMPLE_ROWS } from "../shared/styles";

export default function FDAExport({ facilityId, refreshKey, onEvent, isLoggedIn }) {
  const [rows, setRows] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exportingFormat, setExportingFormat] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");
  const [isDemo, setIsDemo] = useState(!isLoggedIn);

  useEffect(() => {
    if (!isLoggedIn) {
      setRows(FDA_SAMPLE_ROWS);
      setTotalCount(FDA_SAMPLE_ROWS.length);
      setIsDemo(true);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setIsDemo(false);

    (async () => {
      try {
        const preview = await apiClient.getSupplierFDAExportPreview(facilityId || undefined, 50);
        if (!cancelled) {
          setRows(preview.rows || []);
          setTotalCount(preview.total_count || 0);
        }
      } catch {
        if (!cancelled) {
          // Fall back to sample data with label instead of showing an error
          setRows(FDA_SAMPLE_ROWS);
          setTotalCount(FDA_SAMPLE_ROWS.length);
          setIsDemo(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [facilityId, refreshKey, isLoggedIn]);

  const downloadExport = async (format) => {
    if (!isLoggedIn) return;
    setExportingFormat(format);
    setStatusMessage("");
    setError("");
    try {
      const { blob, filename, recordCount } = await apiClient.downloadSupplierFDARecords(format, facilityId || undefined);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setStatusMessage(`Downloaded ${recordCount} record${recordCount === 1 ? "" : "s"} as ${filename}.`);
      onEvent?.({
        event_name: "fda_export_downloaded",
        step: VIEWS.FDA_EXPORT,
        status: "success",
        facility_id: facilityId || undefined,
        metadata: { format, record_count: recordCount, filename },
      });
    } catch {
      setError("Could not generate export file.");
    } finally {
      setExportingFormat(null);
    }
  };

  // Normalize rows: current API rows have different field names than FDA_SAMPLE_ROWS
  const normalizeRow = (row) => ({
    tlc: row.tlc || row.tlc_code || "",
    product: row.product || row.product_description || "-",
    cte: row.cte || row.cte_type || "",
    location: row.location || row.facility_name || "",
    date: (row.date || row.event_time || "").slice(0, 10),
    qty: row.qty || (row.quantity ? `${row.quantity} ${row.unit_of_measure || ""}`.trim() : "-"),
    ref_doc: row.ref_doc || row.reference_document || "-",
    sha256: row.sha256 || (row.payload_sha256 || "").slice(0, 12) + "...",
    id: row.event_id || row.tlc + row.cte + row.date,
  });

  return (
    <div>
      <SectionTitle sub="FDA requires electronic sortable spreadsheet within 24 hours of request">
        Step 8: FDA 24-Hour Export
      </SectionTitle>

      {isDemo && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 6,
          backgroundColor: BLUE_LIGHT, fontSize: 12, color: BLUE,
        }}>
          <strong>Sample data</strong> — This preview shows example FDA export rows. Log in and submit real CTE events to generate your actual export.
        </div>
      )}

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Generate FDA Traceability Records</div>
        <div className="onb-fda-config-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
          {[
            { l: "Date Range", v: "Last 24 months" },
            { l: "TLC Filter", v: "All active TLCs" },
            { l: "CTE Types", v: "All applicable" },
            { l: "Facility", v: "All facilities" },
          ].map((f) => (
            <div key={f.l}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--re-text-secondary)", marginBottom: 2 }}>{f.l}</div>
              <div style={{
                border: `1px solid ${BORDER}`, borderRadius: 8,
                padding: "10px 14px", fontSize: 12,
                color: "var(--re-text-secondary)", backgroundColor: "var(--re-surface-elevated)",
              }}>{f.v}</div>
            </div>
          ))}
        </div>

        <div className="onb-actions-row" style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => downloadExport("xlsx")}
            disabled={exportingFormat !== null || !isLoggedIn}
            style={{
              padding: "10px 20px", borderRadius: 8,
              backgroundColor: ACCENT, color: "var(--re-surface-base)",
              border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer",
              opacity: (exportingFormat || !isLoggedIn) ? 0.6 : 1,
            }}
          >
            {exportingFormat === "xlsx" ? "Preparing XLSX..." : "Export as XLSX (FDA format)"}
          </button>
          <button
            onClick={() => downloadExport("csv")}
            disabled={exportingFormat !== null || !isLoggedIn}
            style={{
              padding: "10px 20px", borderRadius: 8,
              backgroundColor: "transparent", color: "var(--re-text-secondary)",
              border: `1px solid ${BORDER}`, fontWeight: 600, fontSize: 12, cursor: "pointer",
              opacity: (exportingFormat || !isLoggedIn) ? 0.6 : 1,
            }}
          >
            {exportingFormat === "csv" ? "Preparing CSV..." : "Export as CSV"}
          </button>
        </div>

        {statusMessage && (
          <>
            <div style={{ marginTop: 10, fontSize: 12, color: ACCENT }}>{statusMessage}</div>
            <a
              href="/dashboard"
              style={{
                display: "inline-block", padding: "12px 32px", borderRadius: 8,
                background: ACCENT, color: "var(--re-surface-base)",
                fontWeight: 600, fontSize: 15, textDecoration: "none", marginTop: 16,
              }}
            >
              Go to Dashboard →
            </a>
          </>
        )}
        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
      </Card>

      {/* Export preview table */}
      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Export Preview</div>
        {loading && <div style={{ fontSize: 11, color: GRAY, marginBottom: 8 }}>Loading current FDA preview rows...</div>}
        <div className="onb-table-scroll" style={{ border: `1px solid ${BORDER}`, borderRadius: 6, overflow: "hidden", fontSize: 11 }}>
          <div className="onb-fda-grid" style={{
            display: "grid", gridTemplateColumns: "1.4fr 1.4fr 1fr 1.4fr 1.3fr 0.8fr 1fr 1.2fr",
            padding: "6px 8px", backgroundColor: ACCENT,
            color: "var(--re-surface-base)", fontWeight: 600,
          }}>
            <div>TLC</div><div>Product</div><div>CTE</div><div>Location</div><div>Date</div><div>Qty</div><div>Ref Doc</div><div>SHA-256</div>
          </div>
          {rows.map((raw, i) => {
            const row = normalizeRow(raw);
            return (
              <div className="onb-fda-grid" key={row.id || i} style={{
                display: "grid", gridTemplateColumns: "1.4fr 1.4fr 1fr 1.4fr 1.3fr 0.8fr 1fr 1.2fr",
                padding: "6px 8px",
                borderTop: `1px solid ${BORDER}`,
                backgroundColor: i % 2 ? GRAY_LIGHT : "var(--re-surface-base)",
              }}>
                <div style={{ fontFamily: "monospace" }}>{row.tlc}</div>
                <div>{row.product}</div>
                <div>{row.cte}</div>
                <div>{row.location}</div>
                <div>{row.date}</div>
                <div>{row.qty}</div>
                <div>{row.ref_doc}</div>
                <div style={{ fontFamily: "monospace" }}>{row.sha256}</div>
              </div>
            );
          })}
          {rows.length === 0 && (
            <div style={{ padding: "10px 12px", color: GRAY }}>No exportable CTE rows yet. Submit CTE/KDE events first.</div>
          )}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: GRAY }}>
          {totalCount} total rows eligible for FDA export. Every row includes SHA-256 and Merkle linkage for tamper verification.
        </div>
      </Card>

      <InfoCallout>
        The FDA requires a sortable electronic spreadsheet within 24 hours of a records request.
        RegEngine pre-generates this file so you can respond instantly.
      </InfoCallout>
    </div>
  );
}
