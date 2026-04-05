/* ── Design tokens (maps to --re-* CSS custom properties) ────────── */
export const ACCENT      = "var(--re-brand)";
export const ACCENT_LIGHT = "var(--re-brand-muted)";
export const WARN         = "var(--re-warning)";
export const WARN_LIGHT   = "var(--re-warning-muted)";
export const ERROR        = "var(--re-danger)";
export const ERROR_LIGHT  = "var(--re-danger-muted)";
export const BLUE         = "var(--re-info)";
export const BLUE_LIGHT   = "var(--re-info-muted)";
export const GRAY         = "var(--re-text-muted)";
export const GRAY_LIGHT   = "var(--re-surface-card)";
export const BORDER       = "var(--re-surface-border)";

/* ── View identifiers ───────────────────────────────────────────── */
export const VIEWS = {
  OVERVIEW:        "overview",
  HOW_INVITE:      "how_invite",
  HOW_SIGNUP:      "how_signup",
  FACILITY_SETUP:  "facility_setup",
  FTL_SCOPING:     "ftl_scoping",
  CTE_CAPTURE:     "cte_capture",
  TLC_MGMT:        "tlc_mgmt",
  DASHBOARD:       "dashboard",
  FDA_EXPORT:      "fda_export",
};

export const VIEW_STEP_NUMBER = {
  [VIEWS.HOW_INVITE]:     1,
  [VIEWS.HOW_SIGNUP]:     2,
  [VIEWS.FACILITY_SETUP]: 3,
  [VIEWS.FTL_SCOPING]:    4,
  [VIEWS.CTE_CAPTURE]:    5,
  [VIEWS.TLC_MGMT]:       6,
  [VIEWS.DASHBOARD]:      7,
  [VIEWS.FDA_EXPORT]:     8,
};

/* ── FSMA 204 CTE type definitions (matches FDA guidance) ───────── */
export const CTE_TYPES = {
  shipping: {
    label: "Shipping", icon: "📦",
    fields: [
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "pallets", "units"], required: true },
      { name: "product_description", label: "Product Description", type: "text", required: true },
      { name: "ship_from", label: "Ship-From Location", type: "location", required: true },
      { name: "ship_to", label: "Ship-To Location", type: "location", required: true },
      { name: "ship_date", label: "Ship Date", type: "date", required: true },
      { name: "ref_doc_type", label: "Reference Document Type", type: "select", options: ["BOL", "ASN", "Purchase Order", "Invoice"], required: true },
      { name: "ref_doc_number", label: "Reference Document Number", type: "text", required: true },
    ],
  },
  receiving: {
    label: "Receiving", icon: "📥",
    fields: [
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "pallets", "units"], required: true },
      { name: "product_description", label: "Product Description", type: "text", required: true },
      { name: "receiving_location", label: "Receiving Location", type: "location", required: true },
      { name: "date_received", label: "Date Received", type: "date", required: true },
      { name: "previous_source", label: "Immediate Previous Source", type: "location", required: true },
      { name: "ref_doc_type", label: "Reference Document Type", type: "select", options: ["BOL", "ASN", "Purchase Order", "Invoice"], required: true },
      { name: "ref_doc_number", label: "Reference Document Number", type: "text", required: true },
    ],
  },
  transformation: {
    label: "Transformation", icon: "🔄",
    fields: [
      { name: "input_tlc", label: "Input TLC(s)", type: "text", required: true },
      { name: "output_tlc", label: "New TLC (output)", type: "text", required: true },
      { name: "quantity", label: "Output Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "units"], required: true },
      { name: "new_product", label: "New Product Description", type: "text", required: true },
      { name: "transform_location", label: "Transformation Location", type: "location", required: true },
      { name: "transform_date", label: "Transformation Date", type: "date", required: true },
    ],
  },
  harvesting: {
    label: "Harvesting", icon: "🌱",
    fields: [
      { name: "commodity", label: "Commodity", type: "text", required: true },
      { name: "variety", label: "Variety", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "cases", "bins"], required: true },
      { name: "harvest_location", label: "Farm / Field / Growing Area", type: "location", required: true },
      { name: "harvest_date", label: "Harvest Date", type: "date", required: true },
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "subsequent_recipient", label: "Immediate Subsequent Recipient", type: "location", required: true },
    ],
  },
  cooling: {
    label: "Cooling", icon: "❄️",
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
    label: "Initial Packing", icon: "📋",
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
  first_land_based_receiving: {
    label: "First Land-Based Receiving", icon: "🚢",
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
  growing: {
    label: "Growing", icon: "🌾",
    fields: [
      { name: "traceability_lot_code", label: "Traceability Lot Code (TLC)", type: "text", required: true },
      { name: "commodity", label: "Commodity", type: "text", required: true },
      { name: "variety", label: "Variety", type: "text", required: true },
      { name: "quantity", label: "Quantity", type: "number", required: true },
      { name: "unit_of_measure", label: "Unit of Measure", type: "select", options: ["lbs", "kg", "acres", "bins"], required: true },
      { name: "growing_location", label: "Growing Area / Farm", type: "location", required: true },
      { name: "growing_date", label: "Growing Date", type: "date", required: true },
    ],
  },
};

export const FTL_CATEGORIES = [
  { id: "1", name: "Fruits (fresh-cut)", ctes: ["receiving", "transformation", "shipping"] },
  { id: "2", name: "Vegetables (leafy greens)", ctes: ["harvesting", "cooling", "initial_packing", "receiving", "transformation", "shipping"] },
  { id: "3", name: "Shell eggs", ctes: ["initial_packing", "receiving", "shipping"] },
  { id: "4", name: "Nut butter", ctes: ["receiving", "transformation", "shipping"] },
  { id: "5", name: "Fresh herbs", ctes: ["harvesting", "cooling", "initial_packing", "receiving", "shipping"] },
  { id: "6", name: "Finfish (fresh/frozen)", ctes: ["first_land_based_receiving", "receiving", "transformation", "shipping"] },
  { id: "7", name: "Crustaceans (fresh/frozen)", ctes: ["first_land_based_receiving", "receiving", "transformation", "shipping"] },
  { id: "8", name: "Molluscan shellfish", ctes: ["harvesting", "first_land_based_receiving", "receiving", "shipping"] },
  { id: "9", name: "Ready-to-eat deli salads", ctes: ["receiving", "transformation", "shipping"] },
  { id: "10", name: "Soft & semi-soft cheeses", ctes: ["receiving", "transformation", "shipping"] },
];

/* ── FDA Export sample data (shown in demo mode) ────────────────── */
export const FDA_SAMPLE_ROWS = [
  { tlc: "TLC-2026-SAL-0001", product: "Romaine Lettuce", cte: "Shipping", location: "Acme Salinas Packhouse", date: "2026-02-15", qty: "450 cases", ref_doc: "BOL-8834", sha256: "a3f7c9..." },
  { tlc: "TLC-2026-SAL-0001", product: "Romaine Lettuce", cte: "Receiving", location: "FreshCo Dist. Center", date: "2026-02-16", qty: "450 cases", ref_doc: "BOL-8834", sha256: "b2e1d4..." },
  { tlc: "TLC-2026-SAL-0002", product: "Baby Spinach", cte: "Harvesting", location: "Salinas Valley Farm #3", date: "2026-02-17", qty: "200 bins", ref_doc: "HRV-2026-0217", sha256: "c8f2a1..." },
  { tlc: "TLC-2026-SAL-0002", product: "Baby Spinach", cte: "Cooling", location: "Acme Salinas Packhouse", date: "2026-02-17", qty: "200 bins", ref_doc: "CLG-0217-A", sha256: "d4b7e3..." },
  { tlc: "TLC-2026-SAL-0002", product: "Baby Spinach", cte: "Initial Packing", location: "Acme Salinas Packhouse", date: "2026-02-18", qty: "800 cases", ref_doc: "PKG-0218-A", sha256: "e9c3f5..." },
  { tlc: "TLC-2026-SAL-0002", product: "Baby Spinach", cte: "Shipping", location: "Acme Salinas Packhouse", date: "2026-02-18", qty: "800 cases", ref_doc: "BOL-8901", sha256: "f1a6d8..." },
  { tlc: "TLC-2026-WAT-0001", product: "Fresh Basil", cte: "Receiving", location: "Acme Watsonville", date: "2026-02-20", qty: "50 cases", ref_doc: "BOL-9012", sha256: "71b4c2..." },
  { tlc: "TLC-2026-WAT-0001", product: "Fresh Basil", cte: "Shipping", location: "Acme Watsonville", date: "2026-02-21", qty: "50 cases", ref_doc: "BOL-9013", sha256: "82e5d3..." },
];
