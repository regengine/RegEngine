/**
 * Sample CSV datasets for the FSMA 204 sandbox demo.
 *
 * Design principle: these must look like ACTUAL data a mid-market food
 * supply chain company would export from their ERP/WMS. A buyer should
 * see a sample and think "that looks like our data."
 *
 * Authenticity markers:
 *   - Lot codes embed date/product/field/sequence in vendor-specific formats
 *   - GS1 identifiers (GTIN, GLN, SSCC) appear where real companies use them
 *   - Product descriptions include PLU codes, pack configs, case weights
 *   - Quantities use real pack math (cases × count = units)
 *   - Extra columns that RegEngine correctly ignores (PO#, trailer#, etc.)
 *   - Excel export artifacts on the messiest samples (#N/A, trailing commas)
 *   - 30-50 rows on the key samples to feel like real export files
 *
 * Mess levels are graduated so prospects can start simple and ratchet up.
 */

export interface SandboxSample {
  id: string;
  label: string;
  persona: string;
  cteType: string;
  messLevel: string;
  messDescription: string;
  normalizationHits: string[];
  csv: string;
}

export const SANDBOX_SAMPLES: SandboxSample[] = [
  // ═══════════════════════════════════════════════════════════════════
  // 1. HARVESTING — Central Valley grower, 35 rows, hand-entered
  //    Realistic lot codes, field blocks, crew IDs, mixed formats
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "harvesting-grower",
    label: "Grower Harvest Log — 35 Rows",
    persona: "Rio Verde Farms, Salinas CA",
    cteType: "harvesting",
    messLevel: "Low–Medium",
    messDescription: "Hand-entered harvest log with crew IDs, field blocks, mixed dates, and vendor-format lot codes",
    normalizationHits: [
      "Column aliases (Date Picked, Commodity/Variety, Wt, Crew → ignored)",
      "Date parsing (4/10/26, 04/10/2026, April 10 2026, 2026-04-10)",
      "UOM normalization (lb, lbs, Lbs., carton, ctn, bu, bin)",
      "Lot codes with embedded dates (RVF-ROM-041026-F3-001)",
      "Extra columns ignored (Crew, Truck#, Cool ETA)",
      "Entity name variation (Rio Verde Farms vs Rio Verde Farms LLC vs RVF)",
    ],
    csv: `Event Type,Lot #,Commodity/Variety,Wt,Unit,Ranch,Date Picked,Field/Block,Crew,Truck#,Cool ETA,Grower
harvest,RVF-ROM-041026-F3-001,RM HRTS 3PK 24CT,480,carton,Rio Verde Ranch - Salinas,4/10/26,Field 3 Block A,Crew 7,T-114,10:30AM,Rio Verde Farms LLC
harvest,RVF-ROM-041026-F3-002,RM HRTS 3PK 24CT,520,ctn,Rio Verde Ranch - Salinas,04/10/2026,Field 3 Block B,Crew 7,T-114,10:30AM,Rio Verde Farms LLC
harvest,RVF-ROM-041026-F5-001,RM HRTS 3PK 24CT,360,carton,Rio Verde Ranch Salinas,4/10/26,Field 5 Block A,Crew 12,T-116,11:00AM,Rio Verde Farms
harvest,RVF-KALE-041026-F1-001,CURLY KALE 24CT,240,ctn,Rio Verde Ranch - Salinas,2026-04-10,Field 1,Crew 3,T-112,09:45AM,Rio Verde Farms LLC
harvest,RVF-KALE-041026-F1-002,CURLY KALE 24CT,280,carton,Rio Verde Ranch - Salinas,April 10 2026,Field 1 North,Crew 3,T-112,,RVF
harvest,RVF-SPIN-041026-G2-001,BABY SPINACH BULK 20#,600,lb,Rio Verde Ranch Salinas,4/10/26,Greenhouse 2,Crew 9,T-118,10:00AM,Rio Verde Farms LLC
harvest,RVF-SPIN-041026-G2-002,BABY SPINACH BULK 20#,450,lbs,Rio Verde Ranch - Salinas,04/10/2026,Greenhouse 2 East,Crew 9,T-118,10:00AM,Rio Verde Farms LLC
harvest,RVF-SPIN-041026-G3-001,BABY SPINACH BULK 20#,380,Lbs.,Rio Verde Ranch,4/10/26,Greenhouse 3,Crew 9,T-119,10:15AM,Rio Verde Farms
harvest,RVF-CHARD-041026-F2-001,RAINBOW CHARD 12CT,180,ctn,Rio Verde Ranch - Salinas,2026-04-10,Field 2 Block A,Crew 5,T-115,10:45AM,Rio Verde Farms LLC
harvest,RVF-CHARD-041026-F2-002,RAINBOW CHARD 12CT,160,carton,Rio Verde Ranch - Salinas,4/10/26,Field 2 Block B,Crew 5,T-115,10:45AM,Rio Verde Farms LLC
harvest,RVF-CIL-041026-F4-001,CILANTRO BNCH 60CT,120,carton,Rio Verde Ranch,April 10 2026,Field 4,Crew 8,T-117,,Rio Verde Farms LLC
harvest,RVF-ROM-041126-F3-001,RM HRTS 3PK 24CT,500,ctn,Rio Verde Ranch - Salinas,4/11/26,Field 3 Block A,Crew 7,T-114,10:30AM,Rio Verde Farms LLC
harvest,RVF-ROM-041126-F3-002,RM HRTS 3PK 24CT,460,carton,Rio Verde Ranch - Salinas,04/11/2026,Field 3 Block C,Crew 7,T-114,10:30AM,Rio Verde Farms LLC
harvest,RVF-ROM-041126-F5-001,RM HRTS 3PK 24CT,340,ctn,Rio Verde Ranch Salinas,4/11/26,Field 5 Block A,Crew 12,T-116,11:00AM,Rio Verde Farms
harvest,RVF-ROM-041126-F6-001,RM HRTS 3PK 24CT,420,carton,Rio Verde Ranch - Salinas,2026-04-11,Field 6,Crew 12,T-120,11:15AM,Rio Verde Farms LLC
harvest,RVF-KALE-041126-F1-001,CURLY KALE 24CT,300,ctn,Rio Verde Ranch - Salinas,April 11 2026,Field 1,Crew 3,T-112,09:45AM,RVF
harvest,RVF-SPIN-041126-G2-001,BABY SPINACH BULK 20#,550,lb,Rio Verde Ranch Salinas,4/11/26,Greenhouse 2,Crew 9,T-118,10:00AM,Rio Verde Farms LLC
harvest,RVF-SPIN-041126-G3-001,BABY SPINACH BULK 20#,420,lbs,Rio Verde Ranch - Salinas,04/11/2026,Greenhouse 3,Crew 9,T-119,10:15AM,Rio Verde Farms LLC
harvest,RVF-CHARD-041126-F2-001,RAINBOW CHARD 12CT,200,carton,Rio Verde Ranch - Salinas,2026-04-11,Field 2,Crew 5,T-115,10:45AM,Rio Verde Farms LLC
harvest,RVF-CIL-041126-F4-001,CILANTRO BNCH 60CT,140,ctn,Rio Verde Ranch,4/11/26,Field 4,Crew 8,T-117,,Rio Verde Farms LLC
harvest,RVF-ROM-041226-F3-001,RM HRTS 3PK 24CT,480,carton,Rio Verde Ranch - Salinas,4/12/26,Field 3 Block A,Crew 7,T-114,10:30AM,Rio Verde Farms LLC
harvest,RVF-ROM-041226-F3-002,RM HRTS 3PK 24CT,510,ctn,Rio Verde Ranch - Salinas,04/12/2026,Field 3 Block B,Crew 7,T-114,10:30AM,Rio Verde Farms LLC
harvest,RVF-ROM-041226-F5-001,RM HRTS 3PK 24CT,380,carton,Rio Verde Ranch Salinas,4/12/26,Field 5 Block B,Crew 12,T-116,11:00AM,Rio Verde Farms
harvest,RVF-KALE-041226-F1-001,CURLY KALE 24CT,260,carton,Rio Verde Ranch - Salinas,2026-04-12,Field 1 South,Crew 3,T-112,09:45AM,Rio Verde Farms LLC
harvest,RVF-SPIN-041226-G2-001,BABY SPINACH BULK 20#,500,lb,Rio Verde Ranch Salinas,April 12 2026,Greenhouse 2,Crew 9,T-118,10:00AM,Rio Verde Farms LLC
harvest,RVF-SPIN-041226-G3-001,BABY SPINACH BULK 20#,390,lbs,Rio Verde Ranch - Salinas,4/12/26,Greenhouse 3 West,Crew 9,T-119,10:15AM,RVF
harvest,RVF-CHARD-041226-F2-001,RAINBOW CHARD 12CT,190,ctn,Rio Verde Ranch - Salinas,04/12/2026,Field 2 Block A,Crew 5,T-115,10:45AM,Rio Verde Farms LLC
harvest,RVF-CIL-041226-F4-001,CILANTRO BNCH 60CT,110,carton,Rio Verde Ranch,2026-04-12,Field 4 East,Crew 8,T-117,,Rio Verde Farms LLC
harvest,RVF-ROM-041326-F3-001,RM HRTS 3PK 24CT,440,ctn,Rio Verde Ranch - Salinas,4/13/26,Field 3 Block A,Crew 7,T-114,10:30AM,Rio Verde Farms LLC
harvest,RVF-KALE-041326-F1-001,CURLY KALE 24CT,290,carton,Rio Verde Ranch - Salinas,04/13/2026,Field 1,Crew 3,T-112,09:45AM,Rio Verde Farms LLC
harvest,RVF-SPIN-041326-G2-001,BABY SPINACH BULK 20#,480,lb,Rio Verde Ranch Salinas,2026-04-13,Greenhouse 2,Crew 9,T-118,10:00AM,Rio Verde Farms LLC
harvest,RVF-CHARD-041326-F2-001,RAINBOW CHARD 12CT,170,ctn,Rio Verde Ranch - Salinas,April 13 2026,Field 2,Crew 5,T-115,,Rio Verde Farms LLC
harvest,RVF-MGRN-041026-G1-001,MIXED GREENS BULK 10#,800,lb,Rio Verde Ranch - Salinas,4/10/26,Greenhouse 1,Crew 11,T-121,09:30AM,Rio Verde Farms LLC
harvest,RVF-MGRN-041126-G1-001,MIXED GREENS BULK 10#,750,lbs,Rio Verde Ranch,4/11/26,Greenhouse 1,Crew 11,T-121,09:30AM,RVF
harvest,RVF-MGRN-041226-G1-001,MIXED GREENS BULK 10#,820,lb,Rio Verde Ranch - Salinas,04/12/2026,Greenhouse 1 East,Crew 11,T-121,09:30AM,Rio Verde Farms LLC`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 2. COOLING — Cold storage ERP export (kept short for quick demo)
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "cooling-coldstorage",
    label: "Cold Storage — Cooler Records",
    persona: "Arctic Chain Cold Storage",
    cteType: "cooling",
    messLevel: "Low",
    messDescription: "ERP export with missing dates, inconsistent facility names, and temperature readings",
    normalizationHits: [
      "Column aliases (lot → traceability_lot_code, temp → temperature)",
      "Missing KDE (cooling_date absent on row 3)",
      "Entity name inconsistency (Arctic Chain vs ARCTIC CHAIN vs Arctic chain)",
      "UOM normalization (kilogram → kg, Kgs → kg)",
    ],
    csv: `cte,lot,product,qty,uom,facility,cool_date,temp
cooling,RVF-ROM-041026-F3-001,RM HRTS 3PK 24CT,480,carton,Arctic Chain Cold Storage Ctr 7,2026-04-10T10:30:00Z,1.8
cooling,RVF-ROM-041026-F3-002,RM HRTS 3PK 24CT,520,ctn,Arctic chain - Cold Storage Center 7,04/10/2026,2.1
cooling,RVF-SPIN-041026-G2-001,BABY SPINACH BULK 20#,600,lb,ARCTIC CHAIN COLD STORAGE CTR 7,,1.5
cooling,RVF-KALE-041026-F1-001,CURLY KALE 24CT,240,carton,Arctic Chain Ctr7,2026-04-10,2.4
cooling,RVF-CHARD-041026-F2-001,RAINBOW CHARD 12CT,180,ctn,Arctic Chain Cold Storage Ctr 7,April 10 2026,2.0
cooling,RVF-CIL-041026-F4-001,CILANTRO BNCH 60CT,120,carton,Arctic Chain - Ctr 7,2026-04-10T11:00:00Z,2.2`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 3. PACKING — Packhouse ERP, duplicate detection + missing inputs
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "packing-packhouse",
    label: "Packhouse — Packing Records",
    persona: "Valley Fresh Packhouse",
    cteType: "initial_packing",
    messLevel: "Medium",
    messDescription: "ERP export with duplicate rows, missing input lots, PLU codes in product names",
    normalizationHits: [
      "CTE alias (packing → initial_packing)",
      "Column aliases (batch → traceability_lot_code, sku → product_description)",
      "Duplicate row detection (rows 1 & 2 identical)",
      "Missing required KDE (input_lot_codes empty on power greens)",
      "UOM normalization (cs → cases, ea → each, ctn → cartons)",
      "Product names with PLU/pack configs (PLU4060 24CT 3PK)",
    ],
    csv: `cte_type,batch,sku,count,measure,site,date_packed,source_lots
packing,VFP-ROM3P-041026-001,RM HRTS 3PK PLU4640 24CT,960,cs,Valley Fresh Packhouse Line 1,2026-04-10,"RVF-ROM-041026-F3-001,RVF-ROM-041026-F3-002"
packing,VFP-ROM3P-041026-001,RM HRTS 3PK PLU4640 24CT,960,cs,Valley Fresh Packhouse Line 1,2026-04-10,"RVF-ROM-041026-F3-001,RVF-ROM-041026-F3-002"
packing,VFP-SPIN5-041026-001,BABY SPINACH 5OZ CLAM PLU4523,4800,ea,Valley Fresh Packhouse Line 3,04/10/2026,RVF-SPIN-041026-G2-001
packing,VFP-KALE1-041026-001,ORGANIC CURLY KALE 1# BAG PLU4627,480,bag,Valley Fresh Packhouse Line 2,2026-04-10,"RVF-KALE-041026-F1-001,RVF-KALE-041026-F1-002"
packing,VFP-PWRG-041026-001,POWER GREENS MIX 1# PLU4088,500,ctn,Valley Fresh Packhouse,April 10 2026,
packing,VFP-CHRD-041026-001,RAINBOW CHARD BNCH 12CT,340,carton,Valley Fresh Packhouse Line 2,2026-04-10,RVF-CHARD-041026-F2-001
packing,VFP-CIL-041026-001,CILANTRO BNCH 60CT PLU4889,120,ctn,Valley Fresh Packhouse,2026-04-10,RVF-CIL-041026-F4-001`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 4. SHIPPING — Regional distributor WMS export, 40 rows
  //    SSCCs, SCAC codes, trailer numbers, dock assignments
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "shipping-distributor",
    label: "Distributor Shipping — 40 Rows",
    persona: "FreshLine Distribution, Salinas CA",
    cteType: "shipping",
    messLevel: "Medium–High",
    messDescription: "WMS export with SSCCs, carrier SCAC codes, trailer numbers, and missing destinations",
    normalizationHits: [
      "Column aliases (TLC, BOL#, Ship Dt, Dest, SCAC → ignored)",
      "GS1 SSCCs in lot references (00361234500000xxxxx)",
      "Missing required KDE (ship_to empty on 4 rows)",
      "Date parsing (4/11/26, 04/11/2026, 2026-04-11)",
      "UOM normalization (cs → cases, plt → pallets, ea → each)",
      "Extra columns ignored (SCAC, Trailer#, Dock, Temp Set)",
      "Entity name variation (FreshLine vs Freshline vs FRESHLINE)",
      "Carrier name inconsistency (KLLM vs KLLM Transport vs KLLM Logistics)",
    ],
    csv: `type,TLC,Product,Qty,UOM,Ship Dt,Ship From,Dest,Carrier,SCAC,Trailer#,BOL#,Dock,Temp Set
ship,VFP-ROM3P-041026-001,RM HRTS 3PK 24CT,320,cs,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,KLLM Transport,KLLM,TRL-4492,BOL-20260411-001,Dock 3,34F
ship,VFP-ROM3P-041026-001,RM HRTS 3PK 24CT,280,cs,4/11/26,FreshLine Dist Whse Salinas,NorCal Organic Foods Portland,KLLM Transport,KLLM,TRL-4492,BOL-20260411-001,Dock 3,34F
ship,VFP-ROM3P-041026-001,RM HRTS 3PK 24CT,360,cs,04/11/2026,Freshline Dist Whse Salinas,Valley Market Group SF,KLLM Logistics,KLLM,TRL-4493,BOL-20260411-002,Dock 4,34F
ship,VFP-SPIN5-041026-001,BABY SPINACH 5OZ CLAM,2400,ea,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,KLLM Transport,KLLM,TRL-4492,BOL-20260411-001,Dock 3,34F
ship,VFP-SPIN5-041026-001,BABY SPINACH 5OZ CLAM,2400,ea,4/11/26,FreshLine Dist Whse Salinas,,KLLM Transport,KLLM,TRL-4494,BOL-20260411-003,Dock 5,34F
ship,VFP-KALE1-041026-001,ORG CURLY KALE 1# BAG,200,bag,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC LA,KLLM Transport,KLLM,TRL-4492,BOL-20260411-001,Dock 3,34F
ship,VFP-KALE1-041026-001,ORG CURLY KALE 1# BAG,280,bag,04/11/2026,FRESHLINE DIST WHSE SALINAS,NorCal Organic Portland,KLLM,KLLM,TRL-4493,BOL-20260411-002,Dock 4,34F
ship,VFP-PWRG-041026-001,POWER GREENS MIX 1#,250,ctn,2026-04-11,FreshLine Dist Whse Salinas,Valley Market Group SF,KLLM Transport,KLLM,TRL-4493,BOL-20260411-002,Dock 4,34F
ship,VFP-PWRG-041026-001,POWER GREENS MIX 1#,250,ctn,4/11/26,FreshLine Dist Whse Salinas,,KLLM Logistics,KLLM,TRL-4495,BOL-20260411-004,,34F
ship,VFP-CHRD-041026-001,RAINBOW CHARD 12CT,170,carton,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC LA,KLLM Transport,KLLM,TRL-4492,BOL-20260411-001,Dock 3,34F
ship,VFP-CHRD-041026-001,RAINBOW CHARD 12CT,170,ctn,04/11/2026,Freshline Dist Whse Salinas,Bay Area Organic Market,KLLM Transport,KLLM,TRL-4496,BOL-20260411-005,Dock 6,34F
ship,VFP-CIL-041026-001,CILANTRO BNCH 60CT,60,ctn,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,KLLM Transport,KLLM,TRL-4492,BOL-20260411-001,Dock 3,34F
ship,VFP-CIL-041026-001,CILANTRO BNCH 60CT,60,carton,4/11/26,FreshLine Dist Whse Salinas,NorCal Organic Foods Portland,KLLM,KLLM,TRL-4493,BOL-20260411-002,Dock 4,34F
ship,VFP-ROM3P-041126-001,RM HRTS 3PK 24CT,400,cs,2026-04-12,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,Werner Enterprises,WERN,TRL-8810,BOL-20260412-001,Dock 3,34F
ship,VFP-ROM3P-041126-001,RM HRTS 3PK 24CT,350,cs,04/12/2026,FreshLine Dist Whse Salinas,Valley Market Group SF,Werner Enterprises,WERN,TRL-8810,BOL-20260412-001,Dock 3,34F
ship,VFP-ROM3P-041126-001,RM HRTS 3PK 24CT,280,cs,4/12/26,Freshline Dist Whse Salinas,,Werner,WERN,TRL-8811,BOL-20260412-002,Dock 4,34F
ship,VFP-SPIN5-041126-001,BABY SPINACH 5OZ CLAM,3000,ea,2026-04-12,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,Werner Enterprises,WERN,TRL-8810,BOL-20260412-001,Dock 3,34F
ship,VFP-SPIN5-041126-001,BABY SPINACH 5OZ CLAM,2800,ea,04/12/2026,FRESHLINE DIST WHSE SALINAS,NorCal Organic Portland,Werner Enterprises,WERN,TRL-8812,BOL-20260412-003,Dock 5,34F
ship,VFP-KALE1-041126-001,ORG CURLY KALE 1# BAG,150,bag,4/12/26,FreshLine Dist Whse Salinas,Metro Grocery DC LA,Werner Enterprises,WERN,TRL-8810,BOL-20260412-001,Dock 3,34F
ship,VFP-KALE1-041126-001,ORG CURLY KALE 1# BAG,150,bag,2026-04-12,FreshLine Dist Whse Salinas,Valley Market Group SF,Werner,WERN,TRL-8811,BOL-20260412-002,Dock 4,34F
ship,VFP-CHRD-041126-001,RAINBOW CHARD 12CT,100,ctn,04/12/2026,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,Werner Enterprises,WERN,TRL-8810,BOL-20260412-001,Dock 3,34F
ship,VFP-CHRD-041126-001,RAINBOW CHARD 12CT,100,carton,4/12/26,Freshline Dist Whse Salinas,Bay Area Organic Market,Werner Enterprises,WERN,TRL-8813,BOL-20260412-004,Dock 6,34F
ship,VFP-MGRN-041026-001,MIXED GREENS BULK 10#,400,lb,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,KLLM Transport,KLLM,TRL-4492,BOL-20260411-001,Dock 3,34F
ship,VFP-MGRN-041026-001,MIXED GREENS BULK 10#,400,lbs,4/11/26,FreshLine Dist Whse Salinas,,KLLM Transport,KLLM,TRL-4497,BOL-20260411-006,Dock 7,34F
ship,VFP-ROM3P-041226-001,RM HRTS 3PK 24CT,450,cs,2026-04-13,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,Central Refrigerated,CNTL,TRL-2201,BOL-20260413-001,Dock 3,34F
ship,VFP-ROM3P-041226-001,RM HRTS 3PK 24CT,300,cs,04/13/2026,FreshLine Dist Whse Salinas,NorCal Organic Foods Portland,Central Refrigerated,CNTL,TRL-2202,BOL-20260413-002,Dock 4,34F
ship,VFP-SPIN5-041226-001,BABY SPINACH 5OZ CLAM,2600,ea,4/13/26,FRESHLINE DIST WHSE SALINAS,Metro Grocery DC LA,Central Refrigerated,CNTL,TRL-2201,BOL-20260413-001,Dock 3,34F
ship,VFP-KALE1-041226-001,ORG CURLY KALE 1# BAG,130,bag,2026-04-13,FreshLine Dist Whse Salinas,Valley Market Group SF,Central Refrig.,CNTL,TRL-2203,BOL-20260413-003,Dock 5,34F
ship,VFP-KALE1-041226-001,ORG CURLY KALE 1# BAG,130,bag,04/13/2026,Freshline Dist Whse Salinas,,Central Refrigerated,CNTL,TRL-2204,BOL-20260413-004,,34F
ship,VFP-CHRD-041226-001,RAINBOW CHARD 12CT,95,ctn,4/13/26,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,Central Refrigerated,CNTL,TRL-2201,BOL-20260413-001,Dock 3,34F
ship,VFP-CHRD-041226-001,RAINBOW CHARD 12CT,95,carton,2026-04-13,FreshLine Dist Whse Salinas,Bay Area Organic Mkt,Central Refrigerated,CNTL,TRL-2205,BOL-20260413-005,Dock 6,34F
ship,VFP-MGRN-041126-001,MIXED GREENS BULK 10#,375,lb,04/12/2026,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,Werner Enterprises,WERN,TRL-8810,BOL-20260412-001,Dock 3,34F
ship,VFP-MGRN-041126-001,MIXED GREENS BULK 10#,375,lbs,4/12/26,FRESHLINE DIST WHSE SALINAS,NorCal Organic Portland,Werner,WERN,TRL-8814,BOL-20260412-005,Dock 7,34F
ship,VFP-CIL-041126-001,CILANTRO BNCH 60CT,70,ctn,2026-04-12,FreshLine Dist Whse Salinas,Metro Grocery DC LA,Werner Enterprises,WERN,TRL-8810,BOL-20260412-001,Dock 3,34F
ship,VFP-CIL-041126-001,CILANTRO BNCH 60CT,70,carton,04/12/2026,Freshline Dist Whse Salinas,Valley Market Group SF,Werner Enterprises,WERN,TRL-8811,BOL-20260412-002,Dock 4,34F
ship,VFP-MGRN-041226-001,MIXED GREENS BULK 10#,410,lb,2026-04-13,FreshLine Dist Whse Salinas,Metro Grocery DC LA,Central Refrigerated,CNTL,TRL-2201,BOL-20260413-001,Dock 3,34F
ship,VFP-CIL-041226-001,CILANTRO BNCH 60CT,55,ctn,4/13/26,FreshLine Dist Whse Salinas,NorCal Organic Foods Portland,Central Refrigerated,CNTL,TRL-2202,BOL-20260413-002,Dock 4,34F
ship,VFP-CIL-041226-001,CILANTRO BNCH 60CT,55,carton,04/13/2026,FRESHLINE DIST WHSE SALINAS,,Central Refrig.,CNTL,TRL-2206,BOL-20260413-006,,34F`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 5. RECEIVING — Retail DC, 35 rows, legacy WMS with Excel artifacts
  //    GTINs in product codes, PO numbers, #N/A values, temp readings
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "receiving-retailer",
    label: "Retail DC Receiving — 35 Rows",
    persona: "Metro Grocery DC, Los Angeles",
    cteType: "receiving",
    messLevel: "High",
    messDescription: "Legacy WMS export with GTINs, PO#s, #N/A values, product name mismatches, and missing suppliers",
    normalizationHits: [
      "CTE alias (recv → receiving, receipt → receiving)",
      "Column aliases (Vendor Lot#, Item Desc, Rcvd Dt, Supplier, PO# → ignored)",
      "Product name mismatch (RM HRTS 3PK 24CT vs ROMAINE HEARTS 3PK — identity check)",
      "Missing required KDE (previous_source empty on 5 rows)",
      "Excel artifacts (#N/A in temperature column, trailing spaces)",
      "Date parsing (4/12/26, 04/12/2026, 2026-04-12)",
      "UOM normalization (CS → cases, EA → each, CTN → cartons)",
      "GTIN references in product descriptions",
      "Extra columns ignored (PO#, Appt Time, Door#, Recv Clerk)",
    ],
    csv: `Event Type,Vendor Lot#,Item Desc,Qty,UOM,Rcvd Dt,Location,Prev Source,PO#,Ref Doc,Temp °F,Appt Time,Door#,Recv Clerk
recv,VFP-ROM3P-041026-001,RM HRTS 3PK 24CT GTIN-00071430000012,320,CS,2026-04-12,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44210,INV-FL-88401,35.2,06:00,Door 14,J.Martinez
recv,VFP-SPIN5-041026-001,BABY SPINACH 5OZ CLAM PLU4523,2400,EA,04/12/2026,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44210,INV-FL-88401,36.1,06:00,Door 14,J.Martinez
recv,VFP-KALE1-041026-001,ORG CURLY KALE 1# BAG,200,bag,4/12/26,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44210,INV-FL-88401,35.8,06:00,Door 14,J.Martinez
recv,VFP-PWRG-041026-001,POWER GREENS MIX 1#,250,CTN,2026-04-12,Metro Grocery DC Los Angeles,,PO-2026-44211,,#N/A,08:30,Door 16,R.Chen
recv,VFP-CHRD-041026-001,RAINBOW CHARD 12CT,170,carton,04/12/2026,Metro Grocery DC LA,FreshLine Distribution,PO-2026-44210,INV-FL-88401,36.0,06:00,Door 14,J.Martinez
recv,VFP-CIL-041026-001,CILANTRO BNCH 60CT PLU4889,60,CTN,2026-04-12,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44210,INV-FL-88401,35.5,06:00,Door 14,J.Martinez
recv,VFP-MGRN-041026-001,MIXED GREENS BULK 10#,400,LB,4/12/26,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44210,INV-FL-88401,35.9,06:00,Door 14,J.Martinez
receipt,VFP-ROM3P-041126-001,ROMAINE HEARTS 3PK,400,CS,2026-04-13,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44280,INV-FL-88455,35.0,06:30,Door 15,J.Martinez
receipt,VFP-SPIN5-041126-001,BABY SPINACH 5OZ,3000,EA,04/13/2026,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44280,INV-FL-88455,35.4,06:30,Door 15,J.Martinez
receipt,VFP-KALE1-041126-001,ORG CURLY KALE 1# BAG,150,bag,4/13/26,Metro Grocery DC Los Angeles,,PO-2026-44280,,#N/A,06:30,Door 15,J.Martinez
receipt,VFP-CHRD-041126-001,RAINBOW CHARD 12CT,100,ctn,2026-04-13,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44280,INV-FL-88455,35.2,06:30,Door 15,J.Martinez
receipt,VFP-MGRN-041126-001,MIXED GREENS BULK,375,LB,04/13/2026,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44280,INV-FL-88455,35.7,06:30,Door 15,J.Martinez
receipt,VFP-CIL-041126-001,CILANTRO BUNCH 60CT,70,CTN,2026-04-13,Metro Grocery DC Los Angeles,Freshline Dist.,PO-2026-44280,INV-FL-88455,35.1,06:30,Door 15,J.Martinez
recv,VFP-ROM3P-041226-001,RM HRTS 3PK 24CT,450,CS,2026-04-14,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44340,INV-FL-88512,34.8,07:00,Door 14,M.Thompson
recv,VFP-SPIN5-041226-001,BABY SPINACH 5OZ CLAM,2600,EA,04/14/2026,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44340,INV-FL-88512,35.3,07:00,Door 14,M.Thompson
recv,VFP-KALE1-041226-001,ORG CURLY KALE 1#,130,bag,4/14/26,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44340,INV-FL-88512,35.1,07:00,Door 14,M.Thompson
recv,VFP-CHRD-041226-001,RAINBOW CHARD,95,CTN,2026-04-14,Metro Grocery DC LA,,PO-2026-44340,,#N/A,07:00,Door 14,M.Thompson
recv,VFP-MGRN-041226-001,MIXED GREENS 10#,410,LB,04/14/2026,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44340,INV-FL-88512,35.6,07:00,Door 14,M.Thompson
recv,VFP-CIL-041226-001,CILANTRO BNCH,55,ctn,2026-04-14,Metro Grocery DC Los Angeles,Freshline Distribution,PO-2026-44340,INV-FL-88512,35.0,07:00,Door 14,M.Thompson
receipt,EXT-DAI-041226-001,ORG WHOLE MILK 1GAL GTIN-00049000000443,240,CS,2026-04-14,Metro Grocery DC Los Angeles,Heartland Dairy Co-op,PO-2026-44341,INV-HD-2240,38.5,09:00,Door 18,R.Chen
receipt,EXT-DAI-041226-002,ORG 2% MILK 1GAL,240,CS,04/14/2026,Metro Grocery DC Los Angeles,Heartland Dairy Co-op,PO-2026-44341,INV-HD-2240,38.2,09:00,Door 18,R.Chen
recv,EXT-BRD-041226-001,ARTISAN SOURDOUGH LOAF,180,EA,2026-04-14,Metro Grocery DC Los Angeles,,PO-2026-44342,,#N/A,,Door 20,S.Park
recv,EXT-BRD-041226-002,WHOLE WHEAT SANDWICH LOAF,360,EA,4/14/26,Metro Grocery DC Los Angeles,Metro Bakery LLC,PO-2026-44342,INV-MB-1180,,09:30,Door 20,S.Park
recv,EXT-PRO-041226-001,BONELESS SKINLESS CHKN BREAST 40#,80,CS,2026-04-14,Metro Grocery DC Los Angeles,Golden State Poultry Inc,PO-2026-44343,INV-GSP-4401,29.5,05:00,Door 12,J.Martinez
recv,EXT-PRO-041226-002,GROUND TURKEY 93/7 1# ROLL,200,EA,04/14/2026,Metro Grocery DC Los Angeles,Golden State Poultry Inc.,PO-2026-44343,INV-GSP-4401,30.1,05:00,Door 12,J.Martinez
recv,EXT-SEA-041226-001,ATLANTIC SALMON FILLET 8OZ IVP,120,CS,2026-04-14,Metro Grocery DC Los Angeles,Pacific Seafood Group,PO-2026-44344,BOL-PSG-0414,-1.8,04:30,Door 11,J.Martinez
receipt,EXT-SEA-041226-002,COOKED SHRIMP 16/20 2# BAG,150,bag,4/14/26,Metro Grocery DC Los Angeles,Pacific Seafood Group,PO-2026-44344,BOL-PSG-0414,-0.5,04:30,Door 11,J.Martinez
recv,EXT-FRZ-041226-001,FROZEN MIXED VEG 2.5# BAG,300,bag,04/14/2026,Metro Grocery DC Los Angeles,,PO-2026-44345,,0.2,10:00,Door 22,R.Chen
recv,EXT-FRZ-041226-002,FROZEN BROCCOLI FLORETS 2#,250,bag,2026-04-14,Metro Grocery DC Los Angeles,Pacific NW Frozen Foods,PO-2026-44345,INV-PNW-880,-2.0,10:00,Door 22,R.Chen
recv,VFP-ROM3P-041026-001,ROMAINE HRTS 3PK,280,CS,2026-04-12,Metro Grocery DC Los Angeles,Freshline Dist,PO-2026-44212,INV-FL-88402,35.5,10:00,Door 17,M.Thompson
recv,VFP-ROM3P-041026-001,Org Romaine 3pk 24ct,360,cs,04/12/2026,Metro Grocery DC Los Angeles,FreshLine Distribution,PO-2026-44213,INV-FL-88403,35.3,14:00,Door 19,S.Park`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 6. TRANSFORMATION — Food processor production records
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "transformation-processor",
    label: "Food Processor — Production Records",
    persona: "GreenLeaf Processing",
    cteType: "transformation",
    messLevel: "High",
    messDescription: "Production data with missing input lots, mass balance violation, and inconsistent naming",
    normalizationHits: [
      "CTE alias (process → transformation, transform → transformation)",
      "Missing required KDE (input_lot_codes empty — breaks traceability)",
      "Missing transformation_date on row 3",
      "Mass balance violation (output > input quantity)",
      "Input TLC comma parsing (multiple input lots)",
      "Location name variation (GreenLeaf vs Greenleaf vs GREENLEAF)",
    ],
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,transformation_date,input_lots
process,GL-CHPROM-0412-A,CHOPPED ROMAINE 1# BAG PLU4640,2800,bag,GreenLeaf Processing Plant,2026-04-12,"VFP-ROM3P-041026-001,VFP-ROM3P-041126-001"
transform,GL-SPRSAL-0412-A,SPRING SALAD MIX 10OZ CLAM,4000,ea,Greenleaf Processing Plant,04/12/2026,"VFP-SPIN5-041026-001,VFP-MGRN-041026-001"
transformation,GL-KALMX-0412-A,TUSCAN KALE SALAD KIT 12OZ,900,ea,GREENLEAF PROCESSING PLANT,,"VFP-KALE1-041026-001,VFP-CHARD-041026-001"
process,GL-GRJCE-0412-A,GREEN JUICE COLD PRESS 16OZ HPP,2000,bottle,GreenLeaf Processing Plant,2026-04-12,"VFP-SPIN5-041126-001,VFP-KALE1-041126-001,VFP-CIL-041026-001"
transformation,GL-WRPKT-0412-A,VEGGIE WRAP KIT 2CT,600,ea,GreenLeaf Mfg Plant,April 12 2026,`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 7. FIRST LAND-BASED RECEIVING — Seafood dock, worst case
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "flbr-seafood",
    label: "Seafood Dock — Landing Records",
    persona: "Pacific Coast Seafood, Portland OR",
    cteType: "first_land_based_receiving",
    messLevel: "Very High",
    messDescription: "Handwritten dock logs digitized — every kind of data quality issue in one file",
    normalizationHits: [
      "CTE alias (flbr → first_land_based_receiving)",
      "Duplicate row (rows 1 & 2 — same lot, same event)",
      "Lot code O↔0 swap (SHRMP-04O1 — letter O where zero expected)",
      "Unparseable date ('Tues last week' → sentinel + warning)",
      "Missing required KDEs (landing_date, previous_source on various rows)",
      "UOM normalization (pound → lbs, tonne → mt)",
      "Entity name chaos (FV Ocean Harvest vs F/V Ocean Harvest vs FV OceanHarvest)",
    ],
    csv: `cte,lot,product,qty,uom,landing_date,location,previous_source,bol,temp
flbr,SAL-0401-DOCK4-001,ATLANTIC SALMON WHOLE 10-12#,2000,pound,2026-04-01,Pacific Seafood Dock 4 Portland OR,FV Ocean Harvest,BOL-2026-0401-042,-1.5
flbr,SAL-0401-DOCK4-001,ATLANTIC SALMON WHOLE 10-12#,2000,lbs,04/01/2026,Pacific Seafood - Dock 4,F/V Ocean Harvest,BOL-2026-0401-042,-1.5
flbr,TUNA-0401-D2-001,YELLOWFIN TUNA LOIN #1 SASHIMI,800,pound,April 1st 2026,Pacific Seafood Recv Ctr 2,,,
flbr,SHRMP-04O1-D4-001,GULF SHRIMP 16/20CT IQF 5# BAG,1500,lbs,,Pacific Seafood Dock 4 Portland OR,FV Gulf Runner,BOL-2026-0401-043,
flbr,COD-0401-DOCK4-001,PACIFIC COD FILLET SKINLESS 8OZ,1.2,tonne,Tues last week,PACIFIC SEAFOOD DOCK 4,MV Northern Star,BOL-2026-0401-044,-2.1
flbr,CRAB-0401-D3-001,DUNGENESS CRAB WHOLE COOKED,400,lb,2026-04-01,Pacific Seafood Dock 3,FV OceanHarvest,BOL-2026-0401-045,0.2`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 8. FULL SUPPLY CHAIN — Farm to retail, realistic identifiers
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "full-chain",
    label: "Full Supply Chain — Farm to Retail",
    persona: "Romaine traced through 7 CTEs",
    cteType: "mixed",
    messLevel: "Comprehensive",
    messDescription: "One lot traced through 7 CTEs with realistic identifiers and issues at every handoff",
    normalizationHits: [
      "Temporal ordering (harvest → cool → pack → ship → receive → transform → ship → receive)",
      "Identity consistency (RM HRTS 3PK 24CT vs ROMAINE HEARTS 3PK across same TLC)",
      "Mass balance (960 packed → 320 shipped LA + 280 Portland + 360 SF = 960 ✓)",
      "Entity name matching (Rio Verde Farms vs Rio Verde Farms LLC)",
      "Cross-CTE column aliases (different header style per vendor)",
      "Date format chaos (ISO, M/D/YY, 'April 11th' in one file)",
      "UOM normalization (carton, ctn, cs, bag across events)",
      "Missing KDEs scattered across events",
    ],
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,harvest_date,cooling_date,packing_date,ship_date,ship_from_location,ship_to_location,receive_date,receiving_location,immediate_previous_source,reference_document,input_lot_codes,transformation_date
harvesting,RVF-ROM-041026-F3-001,RM HRTS 3PK 24CT,480,carton,Rio Verde Ranch - Salinas,2026-04-10T06:00:00Z,04/10/2026,,,,,,,,,,
cooling,RVF-ROM-041026-F3-001,RM HRTS 3PK 24CT,480,ctn,Arctic Chain Cold Storage Ctr 7,2026-04-10T10:30:00Z,,2026-04-10,,,,,,,,,
initial_packing,VFP-ROM3P-041026-001,RM HRTS 3PK PLU4640 24CT,960,cs,Valley Fresh Packhouse Line 1,2026-04-10T13:00:00Z,,,April 10th 2026,,,,,,,,"RVF-ROM-041026-F3-001,RVF-ROM-041026-F3-002",
shipping,VFP-ROM3P-041026-001,RM HRTS 3PK 24CT,320,cs,FreshLine Dist Whse Salinas,2026-04-11T06:00:00Z,,,,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,,,,BOL-20260411-001,,
receiving,VFP-ROM3P-041026-001,ROMAINE HEARTS 3PK,320,CS,Metro Grocery DC Los Angeles,2026-04-12T08:00:00Z,,,,,,,04/12/2026,Metro Grocery DC Los Angeles,FreshLine Distribution,INV-FL-88401,,
transformation,GL-CHPROM-0412-A,CHOPPED ROMAINE 1# BAG PLU4640,600,bag,GreenLeaf Processing Plant,2026-04-12T12:00:00Z,,,,,,,,,,VFP-ROM3P-041026-001,04/12/2026
shipping,GL-CHPROM-0412-A,CHOPPED ROMAINE 1# BAG,300,bag,GreenLeaf Dist Whse,2026-04-13T06:00:00Z,,,,04/13/2026,GreenLeaf Dist LA,Metro Grocery DC Los Angeles,,,,,
receiving,GL-CHPROM-0412-A,CHPD ROMAINE 1#,295,bag,Metro Grocery DC Los Angeles,2026-04-13T15:00:00Z,,,,,,,2026-04-13,Metro Grocery DC Los Angeles,Greenleaf Processing,PO-2026-44390,,`,
  },

  // ═══════════════════════════════════════════════════════════════════
  // 9. MULTI-VENDOR MIXED CTE — What a DC actually receives
  // ═══════════════════════════════════════════════════════════════════
  {
    id: "multi-vendor-inbound",
    label: "Multi-Vendor — Inbound Receiving",
    persona: "5 Suppliers, 5 Formats, 1 File",
    cteType: "mixed",
    messLevel: "Extreme",
    messDescription: "Five vendors' data merged into one CSV — each uses different column conventions and lot code formats",
    normalizationHits: [
      "CTE alias mixing (receive, receiving, receipt, recv, r)",
      "Date format per vendor (ISO, M/D/YY, 'March 28', 4/4/26)",
      "UOM per vendor (bushel, ea, lb, tote, CS)",
      "Entity name deduplication (same DC, 5 spellings)",
      "Lot code formats from 5 different systems",
      "Missing KDEs vary by vendor",
      "Product names from different master data systems",
    ],
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,receive_date,receiving_location,immediate_previous_source,reference_document,temperature
receiving,APPL-MH-2026-0328,HONEYCRISP APPLES WA EXTRA FANCY 88CT,400,bushel,Metro Dist Ctr Chicago,2026-03-28,Metro Dist. Ctr Chicago,Michigan Harvest Co-Op,PO-2026-3340,2.0
receipt,BRY-PBF-0401-LOT3,BLUEBERRIES 6OZ CLAM PLU4240 12/FLAT,12000,ea,Metro Distribution Cntr Chicago,04/01/2026,Metro Dist Center Chicago,Pacific Berry Farms LLC,INV-PBF-9921,1.8
receive,SAL-ATL-0402-001,ATLANTIC SALMON PORTIONS 8OZ IVP 10# CS,800,lb,Metro Dist. Center Chicago,April 2nd 2026,Metro Dist Ctr Chicago,,BOL-OCN-0402,-1.2
receiving,GRN-MX-04O3-001,MIXED GREENS BULK WASHED 25# TOTE,200,tote,METRO DISTRIBUTION CENTER CHICAGO,2026-04-03,Metro Dist Ctr,Valley Greens LLC,,3.5
r,DAI-HL-0404-A1,ORG WHOLE MILK 1GAL GTIN-00049000000443,240,CS,Metro Dist ctr Chicago,4/4/26,metro dist center chicago,Heartland Dairy Co-op,PO-2026-3399,2.8`,
  },
];

/** The original simple 3-row sample, kept as the default */
export const SAMPLE_CSV_DEFAULT = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,harvest_date,reference_document,cooling_date,ship_date,ship_from_location,ship_to_location,tlc_source_reference,receive_date,receiving_location,immediate_previous_source
harvesting,RVF-ROM-041026-F3-001,RM HRTS 3PK 24CT,480,carton,Rio Verde Ranch - Salinas,2026-04-10T06:00:00Z,2026-04-10,,,,,,,,,
shipping,VFP-ROM3P-041026-001,RM HRTS 3PK 24CT,320,cs,FreshLine Dist Whse Salinas,2026-04-11T06:00:00Z,,BOL-20260411-001,,2026-04-11,FreshLine Dist Whse Salinas,Metro Grocery DC Los Angeles,Valley Fresh Packhouse,,,
receiving,VFP-ROM3P-041026-001,ROMAINE HEARTS 3PK,320,CS,Metro Grocery DC Los Angeles,2026-04-12T08:00:00Z,,INV-FL-88401,,,,,,2026-04-12,Metro Grocery DC Los Angeles,FreshLine Distribution`;
