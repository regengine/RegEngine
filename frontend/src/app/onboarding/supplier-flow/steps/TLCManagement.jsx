/**
 * Step 6: Traceability Lot Code Management (LIVE)
 * Calls apiClient.listSupplierTLCs and apiClient.createSupplierTLC
 */
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { ACCENT, GRAY, GRAY_LIGHT, BORDER, ERROR, BLUE } from "../shared/styles";
import { Card, SectionTitle, Badge, InfoCallout } from "../shared/components";
import { VIEWS } from "../shared/styles";

export default function TLCManagement({ facilityId, refreshKey, onEvent, isLoggedIn }) {
  const [lots, setLots] = useState([]);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newLot, setNewLot] = useState({ tlc_code: "", product_description: "" });

  useEffect(() => {
    if (!isLoggedIn || !facilityId) {
      setLots([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await apiClient.listSupplierTLCs(facilityId);
        if (!cancelled) setLots(data || []);
      } catch {
        if (!cancelled) setError("Could not load TLCs.");
      }
    })();
    return () => { cancelled = true; };
  }, [facilityId, refreshKey, isLoggedIn]);

  const createLot = async () => {
    if (!isLoggedIn) return;
    if (!facilityId || !newLot.tlc_code.trim()) {
      setError("Enter a TLC code and complete facility setup first.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      await apiClient.createSupplierTLC({
        facility_id: facilityId,
        tlc_code: newLot.tlc_code.trim(),
        product_description: newLot.product_description.trim() || undefined,
        status: "active",
      });
      onEvent?.({
        event_name: "tlc_created",
        step: VIEWS.TLC_MGMT,
        status: "success",
        facility_id: facilityId,
        metadata: { tlc_code: newLot.tlc_code.trim() },
      });
      const data = await apiClient.listSupplierTLCs(facilityId);
      setLots(data || []);
      setNewLot({ tlc_code: "", product_description: "" });
    } catch {
      setError("Could not create TLC. It may already exist.");
    } finally {
      setCreating(false);
    }
  };

  if (!facilityId) {
    return (
      <div>
        <SectionTitle sub="TLC is the backbone of FSMA 204 — every CTE record links to a TLC">
          Step 6: Traceability Lot Code Management
        </SectionTitle>
        <Card>
          <div style={{ fontSize: 13, color: GRAY, padding: 20, textAlign: "center" }}>
            Register a facility first, then manage your TLCs here.
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <SectionTitle sub="TLC is the backbone of FSMA 204 — every CTE record links to a TLC">
        Step 6: Traceability Lot Code Management
      </SectionTitle>

      <Card>
        <div className="onb-actions-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Active Traceability Lot Codes</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <input
              value={newLot.tlc_code}
              onChange={(e) => setNewLot((prev) => ({ ...prev, tlc_code: e.target.value }))}
              placeholder="TLC code"
              disabled={!isLoggedIn}
              style={{
                border: `1px solid ${BORDER}`, borderRadius: 8,
                padding: "10px 14px", fontSize: 12,
                color: "var(--re-text-primary)", backgroundColor: "var(--re-surface-elevated)",
              }}
            />
            <input
              value={newLot.product_description}
              onChange={(e) => setNewLot((prev) => ({ ...prev, product_description: e.target.value }))}
              placeholder="Product"
              disabled={!isLoggedIn}
              style={{
                border: `1px solid ${BORDER}`, borderRadius: 8,
                padding: "10px 14px", fontSize: 12,
                color: "var(--re-text-primary)", backgroundColor: "var(--re-surface-elevated)",
              }}
            />
            <button
              onClick={createLot}
              disabled={creating || !isLoggedIn}
              style={{
                padding: "6px 14px", borderRadius: 8,
                backgroundColor: ACCENT, color: "var(--re-surface-base)",
                border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer",
                opacity: (creating || !isLoggedIn) ? 0.6 : 1,
              }}
            >
              {creating ? "Creating..." : "+ Create New TLC"}
            </button>
          </div>
        </div>

        {/* TLC table */}
        <div className="onb-table-scroll" style={{ border: `1px solid ${BORDER}`, borderRadius: 6, overflow: "hidden" }}>
          <div className="onb-tlc-grid" style={{
            display: "grid", gridTemplateColumns: "2fr 2fr 1.5fr 1fr 0.7fr 0.8fr",
            padding: "8px 12px", backgroundColor: GRAY_LIGHT,
            fontSize: 11, fontWeight: 600, color: GRAY,
          }}>
            <div>TLC</div><div>Product</div><div>Facility</div><div>Created</div><div>Events</div><div>Status</div>
          </div>
          {lots.map((lot) => (
            <div className="onb-tlc-grid" key={lot.id} style={{
              display: "grid", gridTemplateColumns: "2fr 2fr 1.5fr 1fr 0.7fr 0.8fr",
              padding: "10px 12px", fontSize: 12,
              borderTop: `1px solid ${BORDER}`, alignItems: "center",
            }}>
              <div style={{ fontFamily: "monospace", fontWeight: 600, color: ACCENT }}>{lot.tlc_code}</div>
              <div>{lot.product_description || "-"}</div>
              <div style={{ color: GRAY }}>{(lot.facility_id || "").slice(0, 8)}...</div>
              <div style={{ color: GRAY }}>{(lot.created_at || "").slice(0, 10)}</div>
              <div style={{ textAlign: "center" }}>{lot.event_count}</div>
              <div><Badge color={lot.status === "active" ? ACCENT : BLUE}>{lot.status}</Badge></div>
            </div>
          ))}
          {lots.length === 0 && (
            <div style={{ padding: "10px 12px", fontSize: 12, color: GRAY }}>
              No TLCs yet. Create one above or submit a CTE with a new TLC code.
            </div>
          )}
        </div>

        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
      </Card>

      <InfoCallout>
        Every CTE event is linked to a TLC in the graph. Forward and backward trace queries traverse
        these edges to reconstruct the full chain of custody for any food product.
      </InfoCallout>
    </div>
  );
}
