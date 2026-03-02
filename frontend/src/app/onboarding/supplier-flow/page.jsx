'use client';

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

const ACCENT = "#1B6B4A";
const ACCENT_LIGHT = "#E8F5EE";
const ACCENT_DARK = "#145236";
const WARN = "#F59E0B";
const WARN_LIGHT = "#FFF8E1";
const ERROR = "#EF4444";
const ERROR_LIGHT = "#FEF2F2";
const BLUE = "#3B82F6";
const BLUE_LIGHT = "#EFF6FF";
const GRAY = "#6B7280";
const GRAY_LIGHT = "#F9FAFB";
const BORDER = "#E5E7EB";

const VIEWS = {
  OVERVIEW: "overview",
  BUYER_INVITE: "buyer_invite",
  SUPPLIER_SIGNUP: "supplier_signup",
  FACILITY_SETUP: "facility_setup",
  FTL_SCOPING: "ftl_scoping",
  CTE_CAPTURE: "cte_capture",
  KDE_FORM: "kde_form",
  TLC_MGMT: "tlc_mgmt",
  DASHBOARD: "dashboard",
  FDA_EXPORT: "fda_export",
  DATA_MODEL: "data_model",
  API_SPEC: "api_spec",
};

const CTE_TYPES = {
  shipping: {
    label: "Shipping",
    icon: "📦",
    fields: [
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "pallets", "units"], required: true },
      { name: "product_description", label: "Product Description", type: "text", required: true },
      { name: "ship_from_location", label: "Ship-From Location", type: "location", required: true },
      { name: "ship_to_location", label: "Ship-To Location", type: "location", required: true },
      { name: "ship_date", label: "Ship Date", type: "date", required: true },
      { name: "ref_doc_type", label: "Reference Document Type", type: "select", options: ["BOL", "Invoice", "PO", "ASN"], required: true },
      { name: "ref_doc_number", label: "Reference Document Number", type: "text", required: true },
    ],
  },
  receiving: {
    label: "Receiving",
    icon: "📥",
    fields: [
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "pallets", "units"], required: true },
      { name: "product_description", label: "Product Description", type: "text", required: true },
      { name: "receiving_location", label: "Receiving Location", type: "location", required: true },
      { name: "date_received", label: "Date Received", type: "date", required: true },
      { name: "previous_source_location", label: "Immediate Previous Source", type: "location", required: true },
      { name: "ref_doc_type", label: "Reference Document Type", type: "select", options: ["BOL", "Invoice", "PO", "ASN"], required: true },
      { name: "ref_doc_number", label: "Reference Document Number", type: "text", required: true },
    ],
  },
  transforming: {
    label: "Transforming",
    icon: "🔄",
    fields: [
      { name: "input_tlc", label: "Input Food TLC", type: "text", required: true },
      { name: "input_product", label: "Input Product Description", type: "text", required: true },
      { name: "input_quantity", label: "Input Quantity + UOM", type: "text", required: true },
      { name: "output_tlc", label: "Output Food TLC (new)", type: "text", required: true },
      { name: "output_product", label: "Output Product Description", type: "text", required: true },
      { name: "output_quantity", label: "Output Quantity + UOM", type: "text", required: true },
      { name: "transform_location", label: "Transform Location", type: "location", required: true },
      { name: "transform_date", label: "Transform Date", type: "date", required: true },
      { name: "ref_doc_type", label: "Reference Document Type", type: "select", options: ["Production Record", "Batch Record", "Work Order"], required: true },
      { name: "ref_doc_number", label: "Reference Document Number", type: "text", required: true },
    ],
  },
  harvesting: {
    label: "Harvesting",
    icon: "🌾",
    fields: [
      { name: "commodity", label: "Commodity", type: "text", required: true },
      { name: "variety", label: "Variety", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "bushels", "bins"], required: true },
      { name: "harvest_location", label: "Farm / Field / Growing Area", type: "location", required: true },
      { name: "harvest_date", label: "Harvest Date", type: "date", required: true },
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "subsequent_recipient", label: "Immediate Subsequent Recipient", type: "location", required: true },
    ],
  },
  cooling: {
    label: "Cooling",
    icon: "❄️",
    fields: [
      { name: "commodity", label: "Commodity", type: "text", required: true },
      { name: "variety", label: "Variety", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "bins"], required: true },
      { name: "traceability_lot_code", label: "TLC (from harvesting)", type: "text", required: true },
      { name: "cooling_location", label: "Cooling Location", type: "location", required: true },
      { name: "cooling_date", label: "Date of Cooling", type: "date", required: true },
      { name: "subsequent_recipient", label: "Immediate Subsequent Recipient", type: "location", required: true },
    ],
  },
  initial_packing: {
    label: "Initial Packing",
    icon: "📋",
    fields: [
      { name: "commodity", label: "Commodity", type: "text", required: true },
      { name: "variety", label: "Variety", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "cartons"], required: true },
      { name: "traceability_lot_code", label: "TLC (assigned at packing)", type: "text", required: true },
      { name: "pack_date", label: "Pack Date", type: "date", required: true },
      { name: "packing_location", label: "Packing Location", type: "location", required: true },
      { name: "subsequent_recipient", label: "Immediate Subsequent Recipient", type: "location", required: true },
    ],
  },
  first_receiver: {
    label: "First Land-Based Receiving",
    icon: "🚢",
    fields: [
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "pallets"], required: true },
      { name: "product_description", label: "Product Description", type: "text", required: true },
      { name: "receiving_location", label: "Receiving Location", type: "location", required: true },
      { name: "date_received", label: "Date Received", type: "date", required: true },
      { name: "previous_source", label: "Immediate Previous Source", type: "location", required: true },
      { name: "ref_doc_type", label: "Reference Document Type", type: "select", options: ["BOL", "Import Entry", "Customs Declaration"], required: true },
      { name: "ref_doc_number", label: "Reference Document Number", type: "text", required: true },
    ],
  },
};

const FTL_CATEGORIES = [
  { id: "1", name: "Fruits (fresh-cut)", ctes: ["receiving", "transforming", "shipping"] },
  { id: "2", name: "Vegetables (leafy greens)", ctes: ["harvesting", "cooling", "initial_packing", "receiving", "transforming", "shipping"] },
  { id: "3", name: "Shell eggs", ctes: ["initial_packing", "receiving", "shipping"] },
  { id: "4", name: "Nut butter", ctes: ["receiving", "transforming", "shipping"] },
  { id: "5", name: "Fresh herbs", ctes: ["harvesting", "cooling", "initial_packing", "receiving", "shipping"] },
  { id: "6", name: "Finfish (fresh/frozen)", ctes: ["first_receiver", "receiving", "transforming", "shipping"] },
  { id: "7", name: "Crustaceans (fresh/frozen)", ctes: ["first_receiver", "receiving", "transforming", "shipping"] },
  { id: "8", name: "Molluscan shellfish", ctes: ["harvesting", "first_receiver", "receiving", "shipping"] },
  { id: "9", name: "Ready-to-eat deli salads", ctes: ["receiving", "transforming", "shipping"] },
  { id: "10", name: "Soft & semi-soft cheeses", ctes: ["receiving", "transforming", "shipping"] },
];

const DASHBOARD_FALLBACK_GAPS = [
  { cte: "Cooling", issue: "No cooling events recorded for TLC-2026-SAL-0001", severity: "high" },
  { cte: "Shipping", issue: "Missing reference document for shipment on 2026-02-28", severity: "medium" },
  { cte: "Receiving", issue: "TLC-2026-WAT-0001 received but no receiving CTE from buyer side", severity: "low" },
];

function Badge({ children, color = ACCENT }) {
  return (
    <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 9999, fontSize: 11, fontWeight: 600, backgroundColor: color === ACCENT ? ACCENT_LIGHT : color === WARN ? WARN_LIGHT : color === ERROR ? ERROR_LIGHT : BLUE_LIGHT, color: color, marginLeft: 6 }}>
      {children}
    </span>
  );
}

function Card({ children, onClick, active, style = {} }) {
  return (
    <div onClick={onClick} style={{ border: `1px solid ${active ? ACCENT : BORDER}`, borderRadius: 8, padding: 16, backgroundColor: active ? ACCENT_LIGHT : "#fff", cursor: onClick ? "pointer" : "default", transition: "all 0.15s", ...style }}>
      {children}
    </div>
  );
}

function SectionTitle({ children, sub }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: "#111", margin: 0 }}>{children}</h2>
      {sub && <p style={{ fontSize: 13, color: GRAY, margin: "4px 0 0" }}>{sub}</p>}
    </div>
  );
}

function FlowStep({ number, title, description, active, onClick, status }) {
  const statusColors = { done: ACCENT, current: BLUE, pending: GRAY };
  const statusBg = { done: ACCENT_LIGHT, current: BLUE_LIGHT, pending: GRAY_LIGHT };
  const c = statusColors[status] || GRAY;
  return (
    <div onClick={onClick} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "12px 16px", borderRadius: 8, border: `1px solid ${active ? c : BORDER}`, backgroundColor: active ? statusBg[status] : "#fff", cursor: "pointer", transition: "all 0.15s" }}>
      <div style={{ width: 28, height: 28, borderRadius: "50%", backgroundColor: c, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
        {status === "done" ? "✓" : number}
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "#111" }}>{title}</div>
        <div style={{ fontSize: 12, color: GRAY, marginTop: 2 }}>{description}</div>
      </div>
    </div>
  );
}

function OverviewView({ setView }) {
  const steps = [
    { id: VIEWS.BUYER_INVITE, n: 1, title: "Buyer Sends Invite", desc: "Email invite with unique onboarding link", status: "current" },
    { id: VIEWS.SUPPLIER_SIGNUP, n: 2, title: "Supplier Creates Account", desc: "Name, email, password - minimal friction", status: "pending" },
    { id: VIEWS.FACILITY_SETUP, n: 3, title: "Facility Registration", desc: "Address, FDA registration #, role in supply chain", status: "pending" },
    { id: VIEWS.FTL_SCOPING, n: 4, title: "FTL Category Scoping", desc: "Select foods handled -> auto-determine CTEs", status: "pending" },
    { id: VIEWS.CTE_CAPTURE, n: 5, title: "CTE/KDE Data Entry", desc: "Dynamic forms per CTE type with validation", status: "pending" },
    { id: VIEWS.TLC_MGMT, n: 6, title: "TLC Management", desc: "Create & track Traceability Lot Codes", status: "pending" },
    { id: VIEWS.DASHBOARD, n: 7, title: "Supplier Dashboard", desc: "Compliance score, submission history, gap alerts", status: "pending" },
    { id: VIEWS.FDA_EXPORT, n: 8, title: "FDA 24-Hour Export", desc: "One-click sortable spreadsheet generation", status: "pending" },
  ];

  return (
    <div>
      <SectionTitle sub="Click any step to see the detailed screen wireframe and data model">Supplier Onboarding Flow - 8 Steps from Invite to FDA-Ready</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {steps.map((s) => (
          <FlowStep key={s.id} number={s.n} title={s.title} description={s.desc} status={s.status} onClick={() => setView(s.id)} />
        ))}
      </div>
      <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
        <Card onClick={() => setView(VIEWS.DATA_MODEL)} style={{ flex: 1, textAlign: "center" }}>
          <div style={{ fontSize: 20 }}>🗄️</div>
          <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>Neo4j Graph Model</div>
        </Card>
        <Card onClick={() => setView(VIEWS.API_SPEC)} style={{ flex: 1, textAlign: "center" }}>
          <div style={{ fontSize: 20 }}>⚡</div>
          <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>API Endpoints</div>
        </Card>
      </div>
    </div>
  );
}

function BuyerInviteView() {
  return (
    <div>
      <SectionTitle sub="Buyer-side action that triggers the supplier onboarding chain">Step 1: Buyer Sends Invite</SectionTitle>
      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: GRAY, marginBottom: 12 }}>BUYER DASHBOARD -&gt; SUPPLIERS -&gt; INVITE</div>
        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, padding: 16, backgroundColor: GRAY_LIGHT }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Invite Supplier</div>
          {[{ l: "Supplier Company Name", p: "Acme Fresh Produce LLC" }, { l: "Contact Email", p: "compliance@acmefresh.com" }, { l: "Contact Name (optional)", p: "Maria Chen" }].map((f) => (
            <div key={f.l} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#333", marginBottom: 3 }}>{f.l}</div>
              <div style={{ border: `1px solid ${BORDER}`, borderRadius: 4, padding: "8px 10px", fontSize: 13, color: GRAY, backgroundColor: "#fff" }}>{f.p}</div>
            </div>
          ))}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#333", marginBottom: 3 }}>FTL Categories You Source From Them</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {["Vegetables (leafy greens)", "Fresh herbs"].map((c) => (
                <span key={c} style={{ padding: "4px 10px", borderRadius: 4, fontSize: 12, backgroundColor: ACCENT_LIGHT, color: ACCENT, fontWeight: 500 }}>{c}</span>
              ))}
              <span style={{ padding: "4px 10px", borderRadius: 4, fontSize: 12, backgroundColor: GRAY_LIGHT, color: GRAY, cursor: "pointer" }}>+ Add category</span>
            </div>
          </div>
          <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 6, backgroundColor: BLUE_LIGHT, fontSize: 12, color: BLUE }}>
            Invite generates a unique link: <code style={{ fontSize: 11 }}>regengine.co/onboard/{"<token>"}</code><br />
            Token encodes: buyer_id, supplier_email, pre-selected FTL categories<br />
            Expires in 30 days. Buyer can resend.
          </div>
          <button style={{ marginTop: 12, padding: "10px 24px", borderRadius: 6, backgroundColor: ACCENT, color: "#fff", border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer" }}>Send Invite</button>
        </div>
      </Card>
      <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 6, backgroundColor: WARN_LIGHT, fontSize: 12, color: "#92400E" }}>
        <strong>Graph effect:</strong> Creates <code>(Buyer)-[:INVITED]-{">"} (PendingSupplier)</code> node in Neo4j with pre-linked FTL categories. Converts to full <code>(:Supplier)</code> on signup.
      </div>
    </div>
  );
}

function SupplierSignupView() {
  return (
    <div>
      <SectionTitle sub="Supplier lands on unique invite link - minimal friction signup">Step 2: Supplier Creates Account</SectionTitle>
      <Card>
        <div style={{ textAlign: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: ACCENT }}>RegEngine</div>
          <div style={{ fontSize: 12, color: GRAY }}>You&apos;ve been invited by <strong>FreshCo Distribution</strong></div>
        </div>
        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, padding: 16, backgroundColor: GRAY_LIGHT }}>
          {[{ l: "Company Name", v: "Acme Fresh Produce LLC", disabled: true }, { l: "Your Name", p: "Maria Chen" }, { l: "Email", v: "compliance@acmefresh.com", disabled: true }, { l: "Password", p: "••••••••••" }, { l: "Role", p: "Select...", type: "select" }].map((f) => (
            <div key={f.l} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#333", marginBottom: 3 }}>{f.l}</div>
              <div style={{ border: `1px solid ${BORDER}`, borderRadius: 4, padding: "8px 10px", fontSize: 13, color: f.disabled ? GRAY : "#333", backgroundColor: f.disabled ? "#f0f0f0" : "#fff" }}>{f.v || f.p}</div>
            </div>
          ))}
          <div style={{ fontSize: 11, color: GRAY, marginTop: 8, marginBottom: 12 }}>
            By signing up you agree to RegEngine&apos;s Terms of Service. Your compliance data is encrypted at rest and in transit.
          </div>
          <button style={{ width: "100%", padding: "10px 24px", borderRadius: 6, backgroundColor: ACCENT, color: "#fff", border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer" }}>Create Account & Continue Setup</button>
        </div>
      </Card>
      <div style={{ marginTop: 12, fontSize: 12, color: GRAY }}>
        <strong>Key decisions:</strong> Company name and email are pre-filled from invite (editable only by buyer). This prevents mismatched supplier records. Password requires 12+ chars (matches existing auth).
      </div>
    </div>
  );
}

function FacilitySetupView({ setView, onFacilityCreated }) {
  const [form, setForm] = useState({
    name: "",
    street: "",
    city: "",
    state: "",
    postal_code: "",
    fda_registration_number: "",
    roles: [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const roleOptions = ["Grower", "Packer", "Processor", "Distributor", "Importer"];

  const toggleRole = (role) => {
    setForm((prev) => ({
      ...prev,
      roles: prev.roles.includes(role)
        ? prev.roles.filter((item) => item !== role)
        : [...prev.roles, role],
    }));
  };

  const saveFacility = async () => {
    setSaving(true);
    setError("");
    try {
      const facility = await apiClient.createSupplierFacility(form);
      onFacilityCreated?.(facility.id);
      setView(VIEWS.FTL_SCOPING);
    } catch (e) {
      setError("Could not save facility. Confirm you are logged in and try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <SectionTitle sub="One supplier can have multiple facilities - each with its own FTL scope">Step 3: Facility Registration</SectionTitle>
      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: GRAY, marginBottom: 12 }}>ADD FACILITY (1 of N)</div>
        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, padding: 16, backgroundColor: GRAY_LIGHT }}>
          {[
            ["Facility Name", "name", "Acme Salinas Packhouse"],
            ["Street Address", "street", "1200 Abbott St"],
            ["City", "city", "Salinas"],
            ["State", "state", "CA"],
            ["ZIP / Postal Code", "postal_code", "93901"],
            ["FDA Registration Number (if applicable)", "fda_registration_number", "12345678901"],
          ].map(([label, key, placeholder]) => (
            <div key={key} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#333", marginBottom: 3 }}>{label}</div>
              <input
                value={form[key]}
                onChange={(event) => setForm((prev) => ({ ...prev, [key]: event.target.value }))}
                placeholder={placeholder}
                style={{ width: "100%", border: `1px solid ${BORDER}`, borderRadius: 4, padding: "8px 10px", fontSize: 13, color: "#111", backgroundColor: "#fff" }}
              />
            </div>
          ))}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#333", marginBottom: 3 }}>Supply Chain Role(s)</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {roleOptions.map((role) => {
                const active = form.roles.includes(role);
                return (
                  <button
                    key={role}
                    onClick={() => toggleRole(role)}
                    style={{ padding: "4px 10px", borderRadius: 4, fontSize: 12, border: `1px solid ${active ? ACCENT : BORDER}`, backgroundColor: active ? ACCENT_LIGHT : "#fff", color: active ? ACCENT : GRAY, cursor: "pointer", fontWeight: 500 }}
                  >
                    {active ? "✓ " : ""}
                    {role}
                  </button>
                );
              })}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button onClick={saveFacility} disabled={saving} style={{ padding: "10px 24px", borderRadius: 6, backgroundColor: ACCENT, color: "#fff", border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer", opacity: saving ? 0.7 : 1 }}>
              {saving ? "Saving..." : "Save & Continue to FTL Scoping"}
            </button>
            <button style={{ padding: "10px 24px", borderRadius: 6, backgroundColor: "#fff", color: GRAY, border: `1px solid ${BORDER}`, fontWeight: 600, fontSize: 13, cursor: "pointer" }}>+ Add Another Facility</button>
          </div>
          {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
        </div>
      </Card>
      <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 6, backgroundColor: ACCENT_LIGHT, fontSize: 12, color: ACCENT_DARK }}>
        <strong>Graph effect:</strong> Creates <code>(Supplier)-[:OPERATES]-{">"} (Facility {"{"} address, fda_reg, roles {"}"})</code>.<br />
        Supply chain roles determine which CTE types are relevant in step 4.
      </div>
    </div>
  );
}

function FTLScopingView({ facilityId, categories, onRequiredCTEsChange }) {
  const [selected, setSelected] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!facilityId) {
      setSelected([]);
      return;
    }

    let cancelled = false;
    const loadExistingScoping = async () => {
      try {
        const data = await apiClient.getFacilityRequiredCTEs(facilityId);
        if (!cancelled) {
          setSelected((data.categories || []).map((category) => category.id));
          onRequiredCTEsChange?.(data.required_ctes || []);
        }
      } catch (_err) {
        if (!cancelled) {
          onRequiredCTEsChange?.([]);
        }
      }
    };

    loadExistingScoping();
    return () => {
      cancelled = true;
    };
  }, [facilityId, onRequiredCTEsChange]);

  const saveScoping = async () => {
    if (!facilityId) {
      setError("Create a facility first to scope FTL categories.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const response = await apiClient.setFacilityFTLCategories(facilityId, { category_ids: selected });
      onRequiredCTEsChange?.(response.required_ctes || []);
    } catch (_err) {
      setError("Could not save category scoping. Confirm you are logged in and try again.");
    } finally {
      setSaving(false);
    }
  };

  if (!facilityId) {
    return (
      <div>
        <SectionTitle sub="This is RegEngine's unique advantage - graph-native FTL scoping auto-determines required CTEs">Step 4: FTL Category Scoping</SectionTitle>
        <Card>
          <div style={{ fontSize: 13, color: GRAY }}>Create a facility in step 3 before assigning FTL categories.</div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <SectionTitle sub="This is RegEngine's unique advantage - graph-native FTL scoping auto-determines required CTEs">Step 4: FTL Category Scoping</SectionTitle>
      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: GRAY, marginBottom: 8 }}>SELECT FOOD TRACEABILITY LIST CATEGORIES HANDLED AT THIS FACILITY</div>
        <div style={{ fontSize: 12, color: GRAY, marginBottom: 12 }}>Pre-selected based on buyer&apos;s invite. Add or remove as needed.</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {(categories?.length ? categories : FTL_CATEGORIES).map((cat) => {
            const active = selected.includes(cat.id);
            return (
              <div key={cat.id} onClick={() => setSelected(active ? selected.filter((s) => s !== cat.id) : [...selected, cat.id])} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", borderRadius: 6, border: `1px solid ${active ? ACCENT : BORDER}`, backgroundColor: active ? ACCENT_LIGHT : "#fff", cursor: "pointer", fontSize: 13 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 18, height: 18, borderRadius: 3, border: `2px solid ${active ? ACCENT : BORDER}`, backgroundColor: active ? ACCENT : "#fff", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11 }}>{active ? "✓" : ""}</span>
                  <span style={{ fontWeight: active ? 600 : 400 }}>{cat.name}</span>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  {cat.ctes.map((cte) => (
                    <span key={cte} style={{ padding: "2px 6px", borderRadius: 3, fontSize: 10, backgroundColor: active ? "#fff" : GRAY_LIGHT, color: active ? ACCENT : GRAY }}>{CTE_TYPES[cte]?.icon} {CTE_TYPES[cte]?.label}</span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <div style={{ marginTop: 12 }}>
          <button onClick={saveScoping} disabled={saving} style={{ padding: "8px 18px", borderRadius: 6, backgroundColor: ACCENT, color: "#fff", border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer", opacity: saving ? 0.7 : 1 }}>
            {saving ? "Saving..." : "Save FTL Scoping"}
          </button>
        </div>
        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
      </Card>
      {selected.length > 0 && (
        <div style={{ marginTop: 12, padding: "12px 14px", borderRadius: 6, backgroundColor: BLUE_LIGHT, fontSize: 12, color: "#1E40AF" }}>
          <strong>Auto-determined CTEs for this facility:</strong>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            {[...new Set(selected.flatMap((id) => FTL_CATEGORIES.find((c) => c.id === id)?.ctes || []))].map((cte) => (
              <span key={cte} style={{ padding: "4px 10px", borderRadius: 4, fontSize: 12, backgroundColor: "#fff", color: BLUE, fontWeight: 600 }}>{CTE_TYPES[cte]?.icon} {CTE_TYPES[cte]?.label}</span>
            ))}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: GRAY }}>Only these CTE forms will appear in data entry. No irrelevant fields.</div>
        </div>
      )}
    </div>
  );
}

function CTECaptureView({ requiredCTEs = [], facilityId, onCTESubmitted }) {
  const availableCTEs = (requiredCTEs.length > 0 ? requiredCTEs : Object.keys(CTE_TYPES)).filter((key) => Boolean(CTE_TYPES[key]));
  const [activeCTE, setActiveCTE] = useState(availableCTEs[0] || "shipping");
  const [formValues, setFormValues] = useState({});
  const [submitResult, setSubmitResult] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!availableCTEs.includes(activeCTE)) {
      setActiveCTE(availableCTEs[0] || "shipping");
    }
  }, [availableCTEs, activeCTE]);

  useEffect(() => {
    setFormValues({});
    setSubmitResult(null);
    setError("");
  }, [activeCTE]);

  const cte = CTE_TYPES[activeCTE];

  const setField = (name, value) => {
    setFormValues((prev) => ({ ...prev, [name]: value }));
  };

  const inferTLC = () => {
    return (
      formValues.traceability_lot_code
      || formValues.output_tlc
      || formValues.input_tlc
      || ""
    );
  };

  const submitCTE = async () => {
    if (!facilityId) {
      setError("Create a facility first, then submit CTE/KDE events.");
      return;
    }

    const tlcCode = inferTLC();
    if (!tlcCode) {
      setError("Enter a Traceability Lot Code before submitting.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const response = await apiClient.submitSupplierCTEEvent(facilityId, {
        cte_type: activeCTE,
        tlc_code: tlcCode,
        kde_data: formValues,
        obligation_ids: [],
      });
      setSubmitResult(response);
      onCTESubmitted?.();
    } catch (_err) {
      setError("Could not submit event. Check required fields and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <SectionTitle sub="Dynamic forms pre-populated with required KDE fields based on CTE type">Step 5: CTE/KDE Data Entry</SectionTitle>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {availableCTEs.map((key) => {
          const val = CTE_TYPES[key];
          if (!val) {
            return null;
          }
          return (
          <button key={key} onClick={() => setActiveCTE(key)} style={{ padding: "6px 12px", borderRadius: 6, border: `1px solid ${activeCTE === key ? ACCENT : BORDER}`, backgroundColor: activeCTE === key ? ACCENT : "#fff", color: activeCTE === key ? "#fff" : GRAY, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>{val.icon} {val.label}</button>
          );
        })}
      </div>
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 20 }}>{cte.icon}</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>New {cte.label} Event</div>
            <div style={{ fontSize: 11, color: GRAY }}>{cte.fields.length} required KDE fields per FSMA 204</div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {cte.fields.map((f) => (
            <div key={f.name}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#333", marginBottom: 2 }}>
                {f.label} {f.required && <span style={{ color: ERROR }}>*</span>}
              </div>
              {f.type === "select" ? (
                <select
                  value={formValues[f.name] || ""}
                  onChange={(event) => setField(f.name, event.target.value)}
                  style={{ width: "100%", border: `1px solid ${BORDER}`, borderRadius: 4, padding: "6px 8px", fontSize: 12, color: "#111", backgroundColor: "#fff" }}
                >
                  <option value="">Select...</option>
                  {(f.options || []).map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              ) : (
                <input
                  type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                  value={formValues[f.name] || ""}
                  onChange={(event) => setField(f.name, event.target.value)}
                  style={{ width: "100%", border: `1px solid ${BORDER}`, borderRadius: 4, padding: "6px 8px", fontSize: 12, color: "#111", backgroundColor: "#fff" }}
                />
              )}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button onClick={submitCTE} disabled={submitting} style={{ padding: "8px 20px", borderRadius: 6, backgroundColor: ACCENT, color: "#fff", border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer", opacity: submitting ? 0.7 : 1 }}>
            {submitting ? "Submitting..." : "Submit & Hash (SHA-256)"}
          </button>
          <button style={{ padding: "8px 20px", borderRadius: 6, backgroundColor: "#fff", color: GRAY, border: `1px solid ${BORDER}`, fontWeight: 600, fontSize: 12, cursor: "pointer" }}>Save Draft</button>
        </div>
        {submitResult && (
          <div style={{ marginTop: 10, fontSize: 11, color: ACCENT_DARK, backgroundColor: ACCENT_LIGHT, borderRadius: 6, padding: "8px 10px" }}>
            Event recorded. SHA-256: <code>{submitResult.payload_sha256.slice(0, 16)}...</code> | Merkle seq: <strong>{submitResult.merkle_sequence}</strong>
          </div>
        )}
        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
      </Card>
      <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
        <div style={{ flex: 1, padding: "8px 12px", borderRadius: 6, backgroundColor: ACCENT_LIGHT, fontSize: 11, color: ACCENT_DARK }}>
          <strong>On submit:</strong> KDE record -&gt; Postgres (source of truth) -&gt; Neo4j (graph linkage to TLC, facility, obligation nodes) -&gt; SHA-256 hash -&gt; Merkle chain append
        </div>
        <div style={{ flex: 1, padding: "8px 12px", borderRadius: 6, backgroundColor: WARN_LIGHT, fontSize: 11, color: "#92400E" }}>
          <strong>Validation:</strong> Required fields, date logic (ship ≤ receive), TLC format check, qty {">"} 0, location must exist in facility registry
        </div>
      </div>
    </div>
  );
}

function TLCMgmtView({ facilityId, refreshKey }) {
  const [lots, setLots] = useState([]);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newLot, setNewLot] = useState({ tlc_code: "", product_description: "" });

  useEffect(() => {
    let cancelled = false;
    const loadLots = async () => {
      if (!facilityId) {
        setLots([]);
        return;
      }
      try {
        const data = await apiClient.listSupplierTLCs(facilityId);
        if (!cancelled) {
          setLots(data || []);
        }
      } catch (_err) {
        if (!cancelled) {
          setError("Could not load TLCs.");
        }
      }
    };
    loadLots();
    return () => {
      cancelled = true;
    };
  }, [facilityId, refreshKey]);

  const createLot = async () => {
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
      const data = await apiClient.listSupplierTLCs(facilityId);
      setLots(data || []);
      setNewLot({ tlc_code: "", product_description: "" });
    } catch (_err) {
      setError("Could not create TLC. It may already exist.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <SectionTitle sub="TLC is the backbone of FSMA 204 - every CTE record links to a TLC">Step 6: Traceability Lot Code Management</SectionTitle>
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Active Traceability Lot Codes</div>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              value={newLot.tlc_code}
              onChange={(event) => setNewLot((prev) => ({ ...prev, tlc_code: event.target.value }))}
              placeholder="TLC code"
              style={{ border: `1px solid ${BORDER}`, borderRadius: 6, padding: "6px 8px", fontSize: 12 }}
            />
            <input
              value={newLot.product_description}
              onChange={(event) => setNewLot((prev) => ({ ...prev, product_description: event.target.value }))}
              placeholder="Product"
              style={{ border: `1px solid ${BORDER}`, borderRadius: 6, padding: "6px 8px", fontSize: 12 }}
            />
            <button onClick={createLot} disabled={creating} style={{ padding: "6px 14px", borderRadius: 6, backgroundColor: ACCENT, color: "#fff", border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer", opacity: creating ? 0.7 : 1 }}>
              {creating ? "Creating..." : "+ Create New TLC"}
            </button>
          </div>
        </div>
        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 2fr 1.5fr 1fr 0.7fr 0.8fr", padding: "8px 12px", backgroundColor: GRAY_LIGHT, fontSize: 11, fontWeight: 600, color: GRAY }}>
            <div>TLC</div><div>Product</div><div>Facility</div><div>Created</div><div>Events</div><div>Status</div>
          </div>
          {lots.map((lot) => (
            <div key={lot.id} style={{ display: "grid", gridTemplateColumns: "2fr 2fr 1.5fr 1fr 0.7fr 0.8fr", padding: "10px 12px", fontSize: 12, borderTop: `1px solid ${BORDER}`, alignItems: "center" }}>
              <div style={{ fontFamily: "monospace", fontWeight: 600, color: ACCENT }}>{lot.tlc_code}</div>
              <div>{lot.product_description || "-"}</div>
              <div style={{ color: GRAY }}>{lot.facility_id.slice(0, 8)}...</div>
              <div style={{ color: GRAY }}>{(lot.created_at || "").slice(0, 10)}</div>
              <div style={{ textAlign: "center" }}>{lot.event_count}</div>
              <div><Badge color={lot.status === "active" ? ACCENT : BLUE}>{lot.status}</Badge></div>
            </div>
          ))}
          {lots.length === 0 && (
            <div style={{ padding: "10px 12px", fontSize: 12, color: GRAY }}>No TLCs yet. Create one or submit a CTE with a new TLC code.</div>
          )}
        </div>
        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
      </Card>
      <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 6, backgroundColor: ACCENT_LIGHT, fontSize: 12, color: ACCENT_DARK }}>
        <strong>Graph model:</strong> <code>(TLC)-[:RECORDED_AT]-{">"} (CTE)-[:HAS_KDE]-{">"} (KDE)</code> and <code>(TLC)-[:PRODUCED_AT]-{">"} (Facility)</code>. Forward/backward trace queries traverse these edges.
      </div>
    </div>
  );
}

function DashboardView({ facilityId, refreshKey }) {
  const [scoreData, setScoreData] = useState(null);
  const [gaps, setGaps] = useState(DASHBOARD_FALLBACK_GAPS);
  const [gapTotal, setGapTotal] = useState(DASHBOARD_FALLBACK_GAPS.length);
  const [tlcCount, setTlcCount] = useState(3);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadDashboard = async () => {
      if (!facilityId) {
        if (!cancelled) {
          setScoreData(null);
          setGaps(DASHBOARD_FALLBACK_GAPS);
          setGapTotal(DASHBOARD_FALLBACK_GAPS.length);
          setTlcCount(3);
        }
        return;
      }

      setLoading(true);
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
            })),
          );
        }
      } catch (_err) {
        if (!cancelled) {
          setScoreData(null);
          setGaps(DASHBOARD_FALLBACK_GAPS);
          setGapTotal(DASHBOARD_FALLBACK_GAPS.length);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadDashboard();

    return () => {
      cancelled = true;
    };
  }, [facilityId, refreshKey]);

  const score = scoreData?.score ?? 73;
  const cteRecordCount = scoreData?.total_events ?? 13;
  return (
    <div>
      <SectionTitle sub="Supplier sees their compliance posture - coverage × effectiveness × freshness">Step 7: Supplier Dashboard</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginBottom: 12 }}>
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
      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Compliance Gaps</div>
        {loading && <div style={{ fontSize: 11, color: GRAY, marginBottom: 8 }}>Refreshing score from live supplier records...</div>}
        {gaps.map((g, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderTop: i > 0 ? `1px solid ${BORDER}` : "none" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: g.severity === "high" ? ERROR : g.severity === "medium" ? WARN : GRAY, flexShrink: 0 }} />
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
      <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 6, backgroundColor: BLUE_LIGHT, fontSize: 12, color: "#1E40AF" }}>
        <strong>Score formula:</strong> coverage (75%) + freshness (15%) + chain integrity (10%).
        {scoreData && (
          <span>
            {" "}Live ratios: coverage {(scoreData.coverage_ratio * 100).toFixed(0)}%, freshness {(scoreData.freshness_ratio * 100).toFixed(0)}%, integrity {(scoreData.integrity_ratio * 100).toFixed(0)}%.
          </span>
        )}
      </div>
    </div>
  );
}

function FDAExportView({ facilityId, refreshKey }) {
  const [rows, setRows] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exportingFormat, setExportingFormat] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const loadPreview = async () => {
      setLoading(true);
      setError("");
      try {
        const preview = await apiClient.getSupplierFDAExportPreview(facilityId || undefined, 50);
        if (!cancelled) {
          setRows(preview.rows || []);
          setTotalCount(preview.total_count || 0);
        }
      } catch (_err) {
        if (!cancelled) {
          setRows([]);
          setTotalCount(0);
          setError("Could not load export preview.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadPreview();

    return () => {
      cancelled = true;
    };
  }, [facilityId, refreshKey]);

  const downloadExport = async (format) => {
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
    } catch (_err) {
      setError("Could not generate export file.");
    } finally {
      setExportingFormat(null);
    }
  };

  return (
    <div>
      <SectionTitle sub="FDA requires electronic sortable spreadsheet within 24 hours of request">Step 8: FDA 24-Hour Export</SectionTitle>
      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Generate FDA Traceability Records</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
          {[
            { l: "Date Range", v: "Last 24 months" },
            { l: "TLC Filter", v: "All active TLCs" },
            { l: "CTE Types", v: "All applicable" },
            { l: "Facility", v: "All facilities" },
          ].map((f) => (
            <div key={f.l}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#333", marginBottom: 2 }}>{f.l}</div>
              <div style={{ border: `1px solid ${BORDER}`, borderRadius: 4, padding: "6px 8px", fontSize: 12, color: "#333", backgroundColor: "#fff" }}>{f.v}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => downloadExport("xlsx")}
            disabled={exportingFormat !== null}
            style={{ padding: "10px 20px", borderRadius: 6, backgroundColor: ACCENT, color: "#fff", border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer", opacity: exportingFormat ? 0.7 : 1 }}
          >
            {exportingFormat === "xlsx" ? "Preparing XLSX..." : "Export as XLSX (FDA format)"}
          </button>
          <button
            onClick={() => downloadExport("csv")}
            disabled={exportingFormat !== null}
            style={{ padding: "10px 20px", borderRadius: 6, backgroundColor: "#fff", color: ACCENT, border: `1px solid ${ACCENT}`, fontWeight: 600, fontSize: 12, cursor: "pointer", opacity: exportingFormat ? 0.7 : 1 }}
          >
            {exportingFormat === "csv" ? "Preparing CSV..." : "Export as CSV"}
          </button>
          <button style={{ padding: "10px 20px", borderRadius: 6, backgroundColor: "#fff", color: GRAY, border: `1px solid ${BORDER}`, fontWeight: 600, fontSize: 12, cursor: "pointer" }}>EPCIS 2.0 (Pro)</button>
        </div>
        {statusMessage && <div style={{ marginTop: 10, fontSize: 12, color: ACCENT }}>{statusMessage}</div>}
        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
      </Card>
      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Export Preview</div>
        {loading && <div style={{ fontSize: 11, color: GRAY, marginBottom: 8 }}>Loading live FDA preview rows...</div>}
        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, overflow: "hidden", fontSize: 11 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1.4fr 1fr 1.4fr 1.3fr 0.8fr 1fr 1.2fr", padding: "6px 8px", backgroundColor: ACCENT, color: "#fff", fontWeight: 600 }}>
            <div>TLC</div><div>Product</div><div>CTE</div><div>Location</div><div>Date</div><div>Qty</div><div>Ref Doc</div><div>SHA-256</div>
          </div>
          {rows.map((row, i) => (
            <div key={row.event_id} style={{ display: "grid", gridTemplateColumns: "1.4fr 1.4fr 1fr 1.4fr 1.3fr 0.8fr 1fr 1.2fr", padding: "6px 8px", borderTop: `1px solid ${BORDER}`, backgroundColor: i % 2 ? GRAY_LIGHT : "#fff" }}>
              <div style={{ fontFamily: "monospace" }}>{row.tlc_code}</div>
              <div>{row.product_description || "-"}</div>
              <div>{row.cte_type}</div>
              <div>{row.facility_name}</div>
              <div>{(row.event_time || "").slice(0, 10)}</div>
              <div>{row.quantity ? `${row.quantity} ${row.unit_of_measure || ""}`.trim() : "-"}</div>
              <div>{row.reference_document || "-"}</div>
              <div style={{ fontFamily: "monospace" }}>{(row.payload_sha256 || "").slice(0, 12)}...</div>
            </div>
          ))}
          {rows.length === 0 && (
            <div style={{ padding: "10px 12px", color: GRAY }}>No exportable CTE rows yet. Submit CTE/KDE events first.</div>
          )}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: GRAY }}>
          {totalCount} total rows eligible for FDA export. Every row includes SHA-256 and Merkle linkage for tamper verification.
        </div>
      </Card>
    </div>
  );
}

function DataModelView() {
  const nodes = [
    { label: "Buyer", props: "id, name, facilities[]", color: BLUE },
    { label: "Supplier", props: "id, name, contact, created_at", color: ACCENT },
    { label: "Facility", props: "id, name, address, fda_reg, roles[]", color: "#8B5CF6" },
    { label: "FTLCategory", props: "id, name, code, applicable_ctes[]", color: WARN },
    { label: "TLC", props: "code, product_desc, created_at, status", color: "#EC4899" },
    { label: "CTEEvent", props: "id, type, timestamp, kde_data{}, sha256_hash", color: ERROR },
    { label: "Obligation", props: "id, cfr_ref, text, must/should", color: GRAY },
  ];
  const edges = [
    "(Buyer)-[:SOURCES_FROM]->(Supplier)",
    "(Supplier)-[:OPERATES]->(Facility)",
    "(Facility)-[:HANDLES]->(FTLCategory)",
    "(FTLCategory)-[:REQUIRES]->(CTEType)",
    "(TLC)-[:PRODUCED_AT]->(Facility)",
    "(CTEEvent)-[:FOR_LOT]->(TLC)",
    "(CTEEvent)-[:OCCURRED_AT]->(Facility)",
    "(CTEEvent)-[:SATISFIES]->(Obligation)",
    "(Obligation)-[:DEFINED_BY]->(Regulation)",
  ];
  return (
    <div>
      <SectionTitle sub="How supplier onboarding data maps to Neo4j graph + Postgres">Neo4j Graph Model</SectionTitle>
      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Node Types</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {nodes.map((n) => (
            <div key={n.label} style={{ padding: "8px 12px", borderRadius: 6, border: `2px solid ${n.color}`, backgroundColor: `${n.color}11` }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: n.color }}>(:{n.label})</div>
              <div style={{ fontSize: 11, color: GRAY, fontFamily: "monospace" }}>{n.props}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Relationships</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {edges.map((e) => (
            <div key={e} style={{ padding: "4px 10px", borderRadius: 4, backgroundColor: GRAY_LIGHT, fontFamily: "monospace", fontSize: 12 }}>{e}</div>
          ))}
        </div>
      </Card>
      <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 6, backgroundColor: ACCENT_LIGHT, fontSize: 12, color: ACCENT_DARK }}>
        <strong>Key insight:</strong> The <code>(CTEEvent)-[:SATISFIES]-{">"} (Obligation)</code> edge is what makes compliance scoring work. Each KDE submission automatically links to the regulatory obligation it satisfies. This is the graph advantage competitors don&apos;t have.
      </div>
    </div>
  );
}

function APISpecView() {
  const endpoints = [
    { method: "POST", path: "/v1/admin/invites", desc: "Buyer sends invite (creates PendingSupplier)", auth: "Buyer JWT", priority: "P0" },
    { method: "POST", path: "/v1/auth/accept-invite", desc: "Supplier completes signup from invite token", auth: "Invite token", priority: "P0" },
    { method: "POST", path: "/v1/supplier/facilities", desc: "Register a facility", auth: "Supplier JWT", priority: "P0" },
    { method: "PUT", path: "/v1/supplier/facilities/{id}/ftl-categories", desc: "Set FTL categories for facility", auth: "Supplier JWT", priority: "P0" },
    { method: "GET", path: "/v1/supplier/facilities/{id}/required-ctes", desc: "Auto-computed from FTL categories", auth: "Supplier JWT", priority: "P0" },
    { method: "POST", path: "/v1/supplier/facilities/{id}/cte-events", desc: "Submit a CTE with KDE data", auth: "Supplier JWT", priority: "P0" },
    { method: "GET", path: "/v1/supplier/tlcs", desc: "List TLCs with status & event counts", auth: "Supplier JWT", priority: "P0" },
    { method: "POST", path: "/v1/supplier/tlcs", desc: "Create new TLC", auth: "Supplier JWT", priority: "P0" },
    { method: "GET", path: "/v1/supplier/compliance-score", desc: "Coverage + freshness + chain integrity", auth: "Supplier JWT", priority: "P0" },
    { method: "GET", path: "/v1/supplier/gaps", desc: "Missing or stale required CTE coverage", auth: "Supplier JWT", priority: "P0" },
    { method: "POST", path: "/v1/supplier/facilities/{id}/cte-events/bulk", desc: "CSV/JSON batch upload", auth: "Supplier JWT", priority: "P1" },
    { method: "GET", path: "/v1/supplier/export/fda-records", desc: "FDA 24-hour sortable spreadsheet", auth: "Supplier JWT", priority: "P0" },
    { method: "GET", path: "/v1/export/epcis", desc: "EPCIS 2.0 XML export", auth: "Pro tier", priority: "P2" },
  ];
  return (
    <div>
      <SectionTitle sub="REST endpoints needed for supplier onboarding V1">API Endpoints</SectionTitle>
      <Card>
        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "0.6fr 2.5fr 2.5fr 1fr 0.6fr", padding: "8px 10px", backgroundColor: GRAY_LIGHT, fontSize: 11, fontWeight: 600, color: GRAY }}>
            <div>Method</div><div>Path</div><div>Description</div><div>Auth</div><div>Priority</div>
          </div>
          {endpoints.map((ep, i) => {
            const methodColors = { GET: BLUE, POST: ACCENT, PUT: WARN, DELETE: ERROR };
            return (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "0.6fr 2.5fr 2.5fr 1fr 0.6fr", padding: "8px 10px", borderTop: `1px solid ${BORDER}`, fontSize: 12, alignItems: "center" }}>
                <div><span style={{ padding: "2px 6px", borderRadius: 3, fontSize: 10, fontWeight: 700, backgroundColor: `${methodColors[ep.method]}18`, color: methodColors[ep.method] }}>{ep.method}</span></div>
                <div style={{ fontFamily: "monospace", fontSize: 11 }}>{ep.path}</div>
                <div style={{ color: GRAY }}>{ep.desc}</div>
                <div style={{ fontSize: 10, color: GRAY }}>{ep.auth}</div>
                <div><Badge color={ep.priority === "P0" ? ERROR : ep.priority === "P1" ? WARN : GRAY}>{ep.priority}</Badge></div>
              </div>
            );
          })}
        </div>
      </Card>
      <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 6, backgroundColor: WARN_LIGHT, fontSize: 12, color: "#92400E" }}>
        <strong>Implementation note:</strong> All P0 endpoints run on current topology (Postgres + Neo4j + Redis). CTE submission writes to Postgres first (source of truth), then async graph sync to Neo4j. No Kafka needed - use Postgres LISTEN/NOTIFY for the async bridge.
      </div>
    </div>
  );
}

export default function SupplierOnboardingFlow() {
  const [view, setView] = useState(VIEWS.OVERVIEW);
  const [facilityId, setFacilityId] = useState(null);
  const [requiredCTEs, setRequiredCTEs] = useState([]);
  const [liveCategories, setLiveCategories] = useState(FTL_CATEGORIES);
  const [tlcRefreshKey, setTlcRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const loadCatalog = async () => {
      try {
        const categories = await apiClient.getFTLCategories();
        if (!cancelled && Array.isArray(categories) && categories.length > 0) {
          setLiveCategories(categories);
        }
      } catch (_err) {
        // Keep local fallback if API catalog is unavailable.
      }
    };

    loadCatalog();
    return () => {
      cancelled = true;
    };
  }, []);

  const navItems = [
    { id: VIEWS.OVERVIEW, label: "Overview", icon: "🏠" },
    { id: VIEWS.BUYER_INVITE, label: "1. Invite", icon: "📧" },
    { id: VIEWS.SUPPLIER_SIGNUP, label: "2. Signup", icon: "👤" },
    { id: VIEWS.FACILITY_SETUP, label: "3. Facility", icon: "🏭" },
    { id: VIEWS.FTL_SCOPING, label: "4. FTL Scope", icon: "🥬" },
    { id: VIEWS.CTE_CAPTURE, label: "5. CTE Entry", icon: "📝" },
    { id: VIEWS.TLC_MGMT, label: "6. TLCs", icon: "🏷️" },
    { id: VIEWS.DASHBOARD, label: "7. Dashboard", icon: "📊" },
    { id: VIEWS.FDA_EXPORT, label: "8. FDA Export", icon: "📄" },
    { id: VIEWS.DATA_MODEL, label: "Graph Model", icon: "🗄️" },
    { id: VIEWS.API_SPEC, label: "API Spec", icon: "⚡" },
  ];

  const viewComponents = {
    [VIEWS.OVERVIEW]: <OverviewView setView={setView} />,
    [VIEWS.BUYER_INVITE]: <BuyerInviteView />,
    [VIEWS.SUPPLIER_SIGNUP]: <SupplierSignupView />,
    [VIEWS.FACILITY_SETUP]: <FacilitySetupView setView={setView} onFacilityCreated={setFacilityId} />,
    [VIEWS.FTL_SCOPING]: <FTLScopingView facilityId={facilityId} categories={liveCategories} onRequiredCTEsChange={setRequiredCTEs} />,
    [VIEWS.CTE_CAPTURE]: <CTECaptureView requiredCTEs={requiredCTEs} facilityId={facilityId} onCTESubmitted={() => setTlcRefreshKey((prev) => prev + 1)} />,
    [VIEWS.TLC_MGMT]: <TLCMgmtView facilityId={facilityId} refreshKey={tlcRefreshKey} />,
    [VIEWS.DASHBOARD]: <DashboardView facilityId={facilityId} refreshKey={tlcRefreshKey + requiredCTEs.length} />,
    [VIEWS.FDA_EXPORT]: <FDAExportView facilityId={facilityId} refreshKey={tlcRefreshKey + requiredCTEs.length} />,
    [VIEWS.DATA_MODEL]: <DataModelView />,
    [VIEWS.API_SPEC]: <APISpecView />,
  };

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "Arial, sans-serif", backgroundColor: "#fff" }}>
      <div style={{ width: 180, backgroundColor: "#111", padding: "16px 0", flexShrink: 0, overflowY: "auto" }}>
        <div style={{ padding: "0 14px 16px", borderBottom: "1px solid #333" }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: ACCENT }}>RegEngine</div>
          <div style={{ fontSize: 10, color: "#888", marginTop: 2 }}>Supplier Onboarding</div>
        </div>
        <div style={{ padding: "8px 0" }}>
          {navItems.map((item) => (
            <div key={item.id} onClick={() => setView(item.id)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px", cursor: "pointer", backgroundColor: view === item.id ? "#222" : "transparent", borderLeft: view === item.id ? `3px solid ${ACCENT}` : "3px solid transparent", transition: "all 0.1s" }}>
              <span style={{ fontSize: 14 }}>{item.icon}</span>
              <span style={{ fontSize: 12, color: view === item.id ? "#fff" : "#999", fontWeight: view === item.id ? 600 : 400 }}>{item.label}</span>
            </div>
          ))}
        </div>
        <div style={{ padding: "12px 14px", borderTop: "1px solid #333", marginTop: 8 }}>
          <div style={{ fontSize: 10, color: "#666", lineHeight: 1.4 }}>
            V1 MVP - runs on current topology<br />
            Postgres + Neo4j + Redis<br />
            No new infrastructure
          </div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
        {viewComponents[view]}
      </div>
    </div>
  );
}
