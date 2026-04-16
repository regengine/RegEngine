/**
 * Sample CSV datasets for the FSMA 204 sandbox demo.
 *
 * Each sample represents a real-world vendor persona exporting data in
 * their own messy format. The samples are designed to trigger every
 * normalization layer RegEngine offers:
 *
 *   ┌─────────────────────────────────────────────────────────────────┐
 *   │  NORMALIZATION LAYER            │  TRIGGERED BY                │
 *   ├─────────────────────────────────┼──────────────────────────────┤
 *   │  Column header aliasing         │  Non-standard column names   │
 *   │  CTE type alias resolution      │  "harvest", "ship", "flbr"  │
 *   │  Date format parsing            │  M/D/YY, "April 2nd", etc.  │
 *   │  UOM normalization              │  "lb", "KG", "cs", "plt"    │
 *   │  Location abbreviation expand   │  "Whse", "Dist", "Mfg"     │
 *   │  Lot code integrity (O↔0, I↔1) │  "L0T", "SHRMP-04O1"       │
 *   │  Required KDE injection         │  Generic date→CTE-specific  │
 *   │  KDE completeness validation    │  Missing ship_to, harvest_d │
 *   │  Temporal ordering              │  Events out of time order   │
 *   │  Identity consistency           │  Product name mismatches    │
 *   │  Mass balance                   │  Output > input quantity    │
 *   │  Duplicate detection            │  Identical rows             │
 *   │  Entity name matching           │  "FreshLine" vs "Freshline" │
 *   │  Input TLC comma parsing        │  "LOT-A,LOT-B,LOT-C"       │
 *   └─────────────────────────────────┴──────────────────────────────┘
 *
 * Mess levels are graduated from Low → Extreme so prospects can start
 * simple and ratchet up complexity to see how RegEngine handles it.
 */

export interface SandboxSample {
  id: string;
  label: string;
  persona: string;
  cteType: string;
  messLevel: string;
  messDescription: string;
  /** Which normalization layers this sample demonstrates */
  normalizationHits: string[];
  csv: string;
}

export const SANDBOX_SAMPLES: SandboxSample[] = [
  // ═══════════════════════════════════════════════════════════════════
  // 1. HARVESTING — Small organic grower using a hand-typed spreadsheet
  //
  // Triggers: column aliases, date format parsing, UOM normalization,
  //           lot code integrity (O↔0 swap), location abbreviation
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "harvesting-grower",
    label: "Organic Grower — Harvest Log",
    persona: "Sunrise Organic Farm",
    cteType: "harvesting",
    messLevel: "Low",
    messDescription: "Hand-typed spreadsheet with date typos, unit abbreviations, and a suspicious lot code",
    normalizationHits: [
      "Column aliases (Date Harvested, Commodity, Weight → canonical fields)",
      "Date parsing (4/1/26, April 1 2026, 2026-04-01)",
      "UOM normalization (lb → lbs, Pound → lbs)",
      "Lot code integrity (ORG-KA1E vs ORG-KALE — I↔1 check)",
      "Location abbreviation (Fac → Facility)",
    ],
    csv: `event_type,Lot Code,Commodity,Weight,Unit,Location,Date Harvested,Growing Area,Grower
harvest,ORG-KALE-0401-001,Organic Curly Kale,1200,lb,Sunrise Organic Farm - Watsonville CA,04/01/2026,North Field Block A,Sunrise Organic Farm LLC
harvest,ORG-KALE-0401-002,Organic Curly Kale,800,Pound,Sunrise Organic Farm  Watsonville CA,4/1/26,North Field Block B,Sunrise Organic Farm LLC
harvest,ORG-SP1N-0401-001,Baby Spinach,2400,lbs,Sunrise Organic Farm Watsonville CA,2026-04-01,East Greenhouse 3,Sunrise Organic Farm LLC
harvest,ORG-CHARD-0401-001,Rainbow Chard,600,Lbs.,Sunrise Organic Fac,April 1 2026,South Terrace,Sunrise Organic Farm LLC`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 2. COOLING — Third-party cold storage facility's ERP export
  //
  // Triggers: column aliases, missing cooling_date (KDE completeness),
  //           location abbreviation, UOM normalization, entity name
  //           inconsistency across rows
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "cooling-coldstorage",
    label: "Cold Storage — Cooler Records",
    persona: "Arctic Chain Cold Storage",
    cteType: "cooling",
    messLevel: "Low–Medium",
    messDescription: "ERP export with missing dates, inconsistent facility names, and temperature as a column",
    normalizationHits: [
      "Column aliases (lot → traceability_lot_code, temp → temperature)",
      "Missing KDE (cooling_date absent on row 3)",
      "Location abbreviation (Ctr → Center)",
      "Entity name inconsistency (Arctic Chain vs ARCTIC CHAIN vs Arctic chain)",
      "UOM normalization (kilogram → kg)",
    ],
    csv: `cte,lot,product,qty,uom,facility,cool_date,temp
cooling,ORG-KALE-0401-001,Organic Curly Kale,544,kilogram,Arctic Chain Cold Storage Ctr 7,2026-04-01T10:30:00Z,1.8
cooling,ORG-KALE-0401-002,Organic Curly Kale,363,kg,Arctic chain - Cold Storage Center 7,04/01/2026,2.1
cooling,ORG-SP1N-0401-001,Baby Spinach,1089,KG,ARCTIC CHAIN COLD STORAGE CTR 7,,1.5
cooling,ORG-CHARD-0401-001,Rainbow Chard,272,Kgs,Arctic Chain Ctr7,April 1st 2026,2.4`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 3. PACKING — Packhouse using custom ERP with non-standard columns
  //
  // Triggers: column aliases, duplicate row detection, missing input
  //           lot codes (required KDE for packing), UOM normalization,
  //           date format parsing, CTE alias
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "packing-packhouse",
    label: "Packhouse — Packing Records",
    persona: "Valley Fresh Packhouse",
    cteType: "initial_packing",
    messLevel: "Medium",
    messDescription: "ERP export with duplicate rows, missing input lots, and mixed column naming",
    normalizationHits: [
      "CTE alias (packing → initial_packing)",
      "Column aliases (batch → traceability_lot_code, item → product_description)",
      "Duplicate row detection (rows 1 & 2 identical)",
      "Missing required KDE (input_lot_codes empty on row 4)",
      "UOM normalization (bag → bags, ea → each, ctn → cartons)",
      "Date parsing (04/02/2026 vs 2026-04-02)",
    ],
    csv: `cte_type,batch,item,count,measure,site,date_packed,source_lots
packing,PKG-KALE-0402-001,Organic Kale 1lb Bag,1100,bag,Valley Fresh Packhouse,2026-04-02,ORG-KALE-0401-001
packing,PKG-KALE-0402-001,Organic Kale 1lb Bag,1100,bag,Valley Fresh Packhouse,2026-04-02,ORG-KALE-0401-001
packing,PKG-SPIN-0402-001,Baby Spinach 5oz Clamshell,4800,ea,Valley Fresh Packhouse,04/02/2026,"ORG-SP1N-0401-001"
packing,PKG-MIX-0402-001,Power Greens Mix 1lb,500,ctn,Valley Fresh Packhouse,April 2nd 2026,
packing,PKG-CHARD-0402-001,Rainbow Chard Bunch 12ct,50,carton,Valley Fresh Packhouse,2026-04-02,ORG-CHARD-0401-001`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 4. SHIPPING — Regional distributor's WMS export
  //
  // Triggers: heavily abbreviated column headers, missing ship_to
  //           (required KDE), mixed date formats, CTE alias,
  //           location abbreviation, UOM normalization, entity name
  //           mismatches, lot code with O↔0 swap
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "shipping-distributor",
    label: "Distributor — Shipping Manifest",
    persona: "FreshLine Distribution",
    cteType: "shipping",
    messLevel: "Medium–High",
    messDescription: "WMS export with abbreviated headers, missing destinations, and inconsistent carrier names",
    normalizationHits: [
      "CTE alias (ship → shipping)",
      "Column aliases (type, tlc, bol, ship_from, ship_to)",
      "Missing required KDE (ship_to_location empty on row 3)",
      "Date parsing (4/3/26, April 3rd 2026)",
      "UOM normalization (cs → cases, plt → pallets)",
      "Location abbreviation (Whse → Warehouse, Dist → Distribution)",
      "Entity name mismatch (Cold Express vs ColdEx vs Cold Express Logistics)",
      "Lot code integrity (PKG-MlX — lowercase L vs 1)",
    ],
    csv: `type,tlc,product,qty,uom,shipping_date,ship_from,ship_to,carrier,bol
ship,PKG-KALE-0402-001,Organic Kale 1lb Bag,500,cs,2026-04-03,FreshLine Dist Whse Salinas,Metro Grocery Whse LA,Cold Express Logistics,BOL-20260403-001
ship,PKG-KALE-0402-001,Organic Kale 1lb Bag,600,cs,04/03/2026,FreshLine Dist Whse Salinas,NorCal Foods Recv Dock Portland,Cold Express,BOL-20260403-002
ship,PKG-SPIN-0402-001,Baby Spinach 5oz Clamshell,4800,each,4/3/26,FreshLine Distribution Warehouse Salinas,,ColdEx,BOL-20260403-003
ship,PKG-MlX-0402-001,Power Greens Mix 1lb,10,plt,April 3rd 2026,Freshline Dist. Whse Salinas,Valley Organics SF,Cold Express Logistics,
ship,PKG-CHARD-0402-001,Chard Bunch 12ct,50,carton,2026-04-03,FreshLine Dist Whse Salinas,Bay Area Organic Market,Cold Express Logistics,BOL-20260403-005`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 5. RECEIVING — Retail DC using legacy system export
  //
  // Triggers: very non-standard column names, missing previous source
  //           (required KDE), quantity mismatch vs shipped qty,
  //           product name inconsistency (identity check), bad UOM,
  //           date parsing, location abbreviation
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "receiving-retailer",
    label: "Retail DC — Receiving Log",
    persona: "Metro Grocery Distribution",
    cteType: "receiving",
    messLevel: "High",
    messDescription: "Legacy system with renamed columns, missing supplier info, product name mismatches",
    normalizationHits: [
      "CTE alias (receipt → receiving)",
      "Column aliases (batch_number, item_description, amount, Vendor → location_name)",
      "Missing required KDE (immediate_previous_source empty on row 2)",
      "Product name mismatch (Organic Kale 1lb Bag vs Org Kale 1# Bag — identity check)",
      "Date parsing (04/04/26, 2026-04-04)",
      "UOM normalization (EA → each, bx → boxes)",
      "Location abbreviation (whse → Warehouse, recv → Receiving)",
      "Missing reference document on row 3",
    ],
    csv: `event_type,batch_number,item_description,amount,unit,received_date,received_at,previous_source,doc_no,temp
receipt,PKG-KALE-0402-001,Organic Kale 1lb Bag,480,case,2026-04-04,Metro Grocery Whse LA,FreshLine Distribution,INV-88321,3.2
receipt,PKG-SPIN-0402-001,Baby Spinach 5oz,4700,EA,04/04/26,Metro Grocery whse LA,,,4.1
receipt,PKG-MlX-0402-001,Power Greens,10,plt,2026-04-04,Metro Grocery Whse LA,Freshline Dist.,,3.8
receipt,PKG-KALE-0402-001,Org Kale 1# Bag,600,bx,2026-04-04,NorCal Foods Recv Dock,FreshLine Distribution,INV-88322,2.9
receipt,PKG-CHARD-0402-001,Chard Bunch 12ct,48,carton,04/04/2026,Bay Area Organic Mkt Recv,FreshLine Distribution,INV-88323,3.1`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 6. TRANSFORMATION — Food processor's production system export
  //
  // Triggers: missing input TLCs (critical for traceability), missing
  //           transformation_date, mass balance violation (output >
  //           input), inconsistent lot code format, CTE alias,
  //           input TLC comma parsing, location name variation
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "transformation-processor",
    label: "Food Processor — Production Records",
    persona: "GreenLeaf Processing",
    cteType: "transformation",
    messLevel: "High",
    messDescription: "Production data with missing input lots, quantity inflation, and inconsistent naming",
    normalizationHits: [
      "CTE alias (process → transformation, transform → transformation)",
      "Column aliases (input_lots → input_traceability_lot_codes)",
      "Missing required KDE (input_lot_codes empty on row 3 — breaks traceability)",
      "Missing transformation_date on row 3",
      "Mass balance violation (row 1: 480+4700=5180 input → 6000 output)",
      "Input TLC comma parsing (multiple input lots)",
      "UOM normalization (unit → units, bag → bags)",
      "Location name variation (GreenLeaf vs Greenleaf vs GREENLEAF)",
      "Lot code format inconsistency (GL-SALAD vs GL_JUICE vs gl-wrap)",
    ],
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,transformation_date,input_lots
process,GL-SALAD-0405-A,Premium Salad Kit 12oz,6000,units,GreenLeaf Processing Plant,2026-04-05,"PKG-KALE-0402-001,PKG-SPIN-0402-001"
transform,GL-SALAD-0405-B,Caesar Salad Kit 10oz,1500,unit,Greenleaf Processing Plant,04/05/2026,PKG-KALE-0402-001
transformation,gl-wrap-0405-A,Veggie Wrap Kit,800,each,GREENLEAF PROCESSING PLANT,,
transformation,GL_JUICE_0405_A,Green Juice Cold Press 16oz,2000,bottles,GreenLeaf Processing Plant,2026-04-05,"PKG-SPIN-0402-001,PKG-MlX-0402-001"
process,GL-CHARD-0405-A,Chard & Kale Sauté Kit,400,bag,GreenLeaf Mfg Plant,April 5th 2026,PKG-CHARD-0402-001`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 7. FIRST LAND-BASED RECEIVING — Seafood dock, handwritten→scanned
  //
  // Triggers: EVERYTHING — this is the worst-case scenario a prospect
  //           would encounter. Bad dates, missing fields, duplicates,
  //           wrong CTE aliases, lot code O↔0 swaps, inconsistent
  //           everything, unparseable date, location abbreviation
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "flbr-seafood",
    label: "Seafood Dock — Landing Records",
    persona: "Pacific Coast Seafood",
    cteType: "first_land_based_receiving",
    messLevel: "Very High",
    messDescription: "Handwritten dock logs digitized — every kind of data quality issue in one file",
    normalizationHits: [
      "CTE alias (flbr → first_land_based_receiving)",
      "Column aliases (lot, bol, temp, previous_source)",
      "Duplicate row (rows 1 & 2 — same lot, same event)",
      "Lot code O↔0 swap (SHRMP-04O1 — letter O where zero expected)",
      "Unparseable date (row 5: 'Tues last week' → sentinel timestamp + warning)",
      "Missing required KDEs (landing_date, previous_source, temperature on various rows)",
      "Location abbreviation (Ctr → Center, Whse → Warehouse)",
      "UOM normalization (pound → lbs, kilo → kg, tonne → mt)",
      "Entity name chaos (FV Ocean Harvest vs F/V Ocean Harvest vs FV OceanHarvest)",
      "All-alpha lot code warning (BATCH on row 6)",
    ],
    csv: `cte,lot,product,qty,uom,landing_date,location,previous_source,bol,temp
flbr,SAL-0401-DOCK4-001,Atlantic Salmon Fillets,2000,pound,2026-04-01,Pacific Seafood Dock 4 Portland OR,FV Ocean Harvest,BOL-2026-0401-042,-1.5
flbr,SAL-0401-DOCK4-001,Atlantic Salmon Fillets,2000,lbs,04/01/2026,Pacific Seafood - Dock 4,F/V Ocean Harvest,BOL-2026-0401-042,-1.5
flbr,TUNA-0401-D2-001,Yellowfin Tuna Loin,800,pound,April 1st 2026,Pacific Seafood Recv Ctr 2,,,
flbr,SHRMP-04O1-D4-001,Gulf Shrimp 16/20ct,1500,lbs,,Pacific Seafood Dock 4 Portland OR,FV Gulf Runner,BOL-2026-0401-043,
flbr,COD-0401-DOCK4-001,Pacific Cod Fillets,1.2,tonne,Tues last week,PACIFIC SEAFOOD DOCK 4,MV Northern Star,BOL-2026-0401-044,-2.1
flbr,BATCH,Misc Bycatch,200,kilo,2026-04-01,Pacific Seafood Whse 1,FV OceanHarvest,,0.2`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 8. FULL SUPPLY CHAIN — One product traced farm-to-retail
  //
  // Triggers: temporal ordering validation (events must follow supply
  //           chain lifecycle), identity consistency (product name
  //           variations across same TLC), mass balance (quantity
  //           shrinkage is expected but must be within tolerance),
  //           entity name matching across handoffs, every date/UOM/
  //           header normalization from prior samples, plus a
  //           transformation that combines two input lots
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "full-chain",
    label: "Full Supply Chain — Farm to Retail",
    persona: "End-to-End Romaine Trace",
    cteType: "mixed",
    messLevel: "Comprehensive",
    messDescription: "One lot traced through 7 CTEs with issues at every handoff — the ultimate stress test",
    normalizationHits: [
      "Temporal ordering (events must follow harvest→cool→pack→ship→receive→transform→ship→receive)",
      "Identity consistency (Romaine Lettuce Hearts vs Romaine Lettuce vs romaine hearts across same TLC)",
      "Mass balance (3000 harvested → 2950 received → 2800 packed — within tolerance?)",
      "Entity name matching (Coastline Farms vs Coastline farms vs COASTLINE FARMS)",
      "Cross-CTE column aliases (different header style per vendor in same file)",
      "Date format chaos (ISO, M/D/YY, 'April 11th', etc. — all in one file)",
      "UOM normalization (lb, lbs, Lbs, pound across events)",
      "Location abbreviation (Dist, Whse, Mfg, Recv across events)",
      "Missing KDEs scattered across events",
      "Transformation input TLC linking",
    ],
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,harvest_date,cooling_date,packing_date,ship_date,ship_from_location,ship_to_location,receive_date,receiving_location,immediate_previous_source,reference_document,input_lot_codes,transformation_date
harvesting,ROM-0410-F1-001,Romaine Lettuce Hearts,3000,lb,Coastline Farms Salinas CA,2026-04-10T06:00:00Z,04/10/2026,,,,,,,,,,
cooling,ROM-0410-F1-001,Romaine Lettuce Hearts,3000,lbs,Coastline Farms Cooler #1,2026-04-10T09:00:00Z,,2026-04-10,,,,,,,,,
initial_packing,ROM-0410-F1-001,Romaine Hearts 3-Pack,2800,bag,Coastline Farms Packhouse,2026-04-10T13:00:00Z,,,April 10th 2026,,,,,,,,
shipping,ROM-0410-F1-001,Romaine Lettuce Hearts,2800,bags,Coastline Farms Dist Whse,2026-04-10T16:00:00Z,,,,2026-04-10,Coastline Farms Salinas,FreshCo Dist Whse LA,,,,BOL-9910,,
receiving,ROM-0410-F1-001,Romaine Lettuce,2780,bags,FreshCo Dist Whse LA,2026-04-11T08:00:00Z,,,,,,,04/11/2026,FreshCo Dist. Whse LA,Coastline farms,INV-20261011,,
transformation,CHOP-ROM-0411-001,Chopped Romaine 1lb Bag,2700,bags,FreshCo Mfg Plant,2026-04-11T12:00:00Z,,,,,,,,,,ROM-0410-F1-001,04/11/2026
shipping,CHOP-ROM-0411-001,Chopped Romaine 1lb bag,1400,bag,FreshCo Dist Whse LA,2026-04-12T06:00:00Z,,,,04/12/2026,FreshCo Dist LA,GreenMart Regional Whse,,,,,
receiving,CHOP-ROM-0411-001,Chopped Romaine 1lb Bag,1380,bags,GreenMart Regional Whse,2026-04-12T15:00:00Z,,,,,,,2026-04-12,GreenMart Regional Whse,FreshCo Distribution,PO-55123,,`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 9. MULTI-VENDOR MIXED CTE — What a distributor receives from
  //    5 different suppliers, each with their own column naming
  //
  // Triggers: every column alias pattern colliding in one file,
  //           CTE type mixing, entity deduplication challenge,
  //           mass balance across supplier handoffs
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "multi-vendor-inbound",
    label: "Multi-Vendor — Inbound Receiving",
    persona: "5 Suppliers, 5 Formats, 1 File",
    cteType: "mixed",
    messLevel: "Extreme",
    messDescription: "Five vendors' data merged into one CSV — each row uses different column conventions",
    normalizationHits: [
      "Every column alias pattern in one file",
      "CTE alias mixing (receive, receiving, receipt, r)",
      "Date format per vendor (ISO, M/D/YY, 'March 28', epoch-adjacent)",
      "UOM per vendor (lbs, kg, cases, bushel, tote)",
      "Entity name deduplication (same supplier, 5 spellings)",
      "Location abbreviation across all vendors",
      "Lot code formats from 5 different systems",
      "Missing KDEs vary by vendor",
      "Product description inconsistency for same commodity",
    ],
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,receive_date,receiving_location,immediate_previous_source,reference_document,temperature
receiving,APPL-MH-2026-0328,Honeycrisp Apples,400,bushel,Metro Dist Ctr Chicago,2026-03-28,Metro Dist. Ctr Chicago,Michigan Harvest Co-Op,PO-2026-3340,2.0
receipt,BRY-0401-WA-LOT3,Blueberries 6oz Clamshell,12000,ea,Metro Distribution Cntr Chicago,04/01/2026,Metro Dist Center Chicago,Pacific Berry Farms LLC,INV-PBF-9921,1.8
receive,SAL-ATL-0402-001,Atlantic Salmon Portions 8oz,800,lb,Metro Dist. Center Chicago,April 2nd 2026,Metro Dist Ctr Chicago,,BOL-OCN-0402,-1.2
receiving,GRN-MX-04O3-001,Mixed Greens Bulk,200,tote,METRO DISTRIBUTION CENTER CHICAGO,2026-04-03,Metro Dist Ctr,Valley Greens LLC,,3.5
r,DAI-MLK-0404-A1,Organic Whole Milk 1gal,2400,unit,Metro Dist ctr Chicago,4/4/26,metro dist center chicago,Heartland Dairy Co-op,PO-2026-3399,2.8`,
  },
];

/** The original simple 3-row sample, kept as the default */
export const SAMPLE_CSV_DEFAULT = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,harvest_date,reference_document,cooling_date,ship_date,ship_from_location,ship_to_location,tlc_source_reference,receive_date,receiving_location,immediate_previous_source
harvesting,LOT-2026-001,Romaine Lettuce,2000,lbs,Valley Fresh Farms,2026-03-12T08:00:00Z,2026-03-12,,,,,,,,,
shipping,LOT-2026-001,Romaine Lettuce,2000,lbs,Valley Fresh DC,2026-03-13T06:00:00Z,,BOL-4421,,,Valley Fresh Farms,FreshCo Distribution,Valley Fresh Farms LLC,,,
receiving,LOT-2026-001,Romaine Lettuce,1900,lbs,FreshCo Distribution,2026-03-13T14:00:00Z,,INV-8832,,,,,,2026-03-13,FreshCo DC East,Valley Fresh Farms LLC`;
