/**
 * Step 7: Supplier Dashboard (LIVE)
 * Calls apiClient.getSupplierComplianceScore, getSupplierComplianceGaps, listSupplierTLCs
 *
 * KEY FIX: No silent fake data. When logged out or API fails, shows an explicit
 * "Demo preview" label so the user always knows what's real vs sample.
 */
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { ACCENT, GRAY, GRAY_LIGHT, BORDER, ERROR, BLUE, BLUE_LIGHT, WARN } from "../shared/styles";
import { Card, SectionTitle, InfoCallout } from "../shared/components";

const DEMO_GAPS = [
  { cte: "Receiving", issue: "No receiving CTE recorded for TLC-2026-SAL-0001", severity: "high" },
  { cte: "Shipping", issue: "Missing reference document on 2 shipping events", severity: "medium" },
  { cte: "Scoping", issue: "No FTL categories scoped for Facility #2", severity: "high" },
];

export default function Dashboard({ facilityId, refreshKey, isLoggedIn }) {
  const [scoreData, setScoreData] = useState(null);
  const [gaps, setGaps] = useState([]);
  const [gapTotal, setGapTotal] = useState(0);
  const [tlcCount, setTlcCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [isDemo, setIsDemo] = useState(!isLoggedIn);

  useEffect(() => {
    if (!isLoggedIn || !facilityId) {
      setScoreData(null);
      setGaps(DEMO_GAPS);
      setGapTotal(DEMO_GAPS.length);
      setTlcCount(3);
      setIsDemo(true);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setIsDemo(false);

    (async () => {
      try {
        const [scoreResponse, gapResponse, tlcs] = await Promise.all([
          apiClient.getSupplierComplianceScore(facilityId),
          apiClient.getSupplierComplianceGaps(facilityId),
          apiClient.listSupplierTLCs(facilityId),
        ]);
        if (!cancelled) {
          setScoreData(scoreResponse);
          setGapTotal(gapResponse.total || 0);
          setTlcCount((tlcs || []).length);
          setGaps(
            (gapResponse.gaps || []).map((gap) => ({
              cte: gap.cte_type ? gap.cte_type.replaceAll("_", " ") : "Scoping",
              issue: gap.issue,
              severity: gap.severity,
            }))
          );
        }
      } catch {
        if (!cancelled) {
          setScoreData(null);
          setGaps(DEMO_GAPS);
          setGapTotal(DEMO_GAPS.length);
          setIsDemo(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [facilityId, refreshKey, isLoggedIn]);

  const score = scoreData?.score ?? 73;
  const cteRecordCount = scoreData?.total_events ?? 13;

  return (
    <div>
      <SectionTitle sub="Your compliance posture — coverage, freshness, and chain integrity">
        Step 7: Supplier Dashboard
      </SectionTitle>

      {isDemo && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 6,
          backgroundColor: BLUE_LIGHT, fontSize: 12, color: BLUE,
        }}>
          <strong>Demo preview</strong> — These are sample metrics. Log in and complete the previous steps to see your real compliance data.
        </div>
      )}

      {/* Metric cards */}
      <div className="onb-dashboard-metrics" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginBottom: 12 }}>
        {[
          { label: "Compliance Score", value: `${score}%`, color: score >= 80 ? ACCENT : WARN },
          { label: "Active TLCs", value: `${tlcCount}`, color: BLUE },
          { label: "CTE Records", value: `${cteRecordCount}`, color: ACCENT },
          { label: "Open Gaps", value: `${gapTotal}`, color: ERROR },
        ].map((m) => (
          <Card key={m.label} style={{ textAlign: "center", padding: 12 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: m.color }}>{m.value}</div>
            <div style={{ fontSize: 11, color: GRAY, marginTop: 2 }}>{m.label}</div>
          </Card>
        ))}
      </div>

      {/* Gaps table */}
      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Compliance Gaps</div>
        {loading && <div style={{ fontSize: 11, color: GRAY, marginBottom: 8 }}>Refreshing score from live supplier records...</div>}
        {gaps.map((g, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "8px 0",
            borderTop: i > 0 ? `1px solid ${BORDER}` : "none",
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
              backgroundColor: g.severity === "high" ? ERROR : g.severity === "medium" ? WARN : GRAY,
            }} />
            <div>
              <div style={{ fontSize: 12, fontWeight: 600 }}>{g.cte}</div>
              <div style={{ fontSize: 11, color: GRAY }}>{g.issue}</div>
            </div>
          </div>
        ))}
        {gaps.length === 0 && (
          <div style={{ fontSize: 12, color: ACCENT }}>No open gaps for scoped CTE obligations.</div>
        )}
      </Card>

      <InfoCallout>
        Compliance score = coverage (75%) + freshness (15%) + chain integrity (10%).
        {scoreData && (
          <span>
            {" "}Live ratios: coverage {(scoreData.coverage_ratio * 100).toFixed(0)}%, freshness {(scoreData.freshness_ratio * 100).toFixed(0)}%, integrity {(scoreData.integrity_ratio * 100).toFixed(0)}%.
          </span>
        )}
      </InfoCallout>
    </div>
  );
}
