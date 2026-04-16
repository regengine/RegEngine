/**
 * Sample CSV datasets for the FSMA 204 sandbox demo.
 *
 * Each sample represents a different supply-chain vendor persona with
 * graduated levels of data messiness — from nearly clean (harvesting)
 * to heavily flawed (first land-based receiving).
 *
 * Mess types progress through:
 *   1. Harvesting   → minor UOM abbreviation, slightly odd date format
 *   2. Cooling      → missing cooling_date on one row, inconsistent location names
 *   3. Packing      → duplicate row, missing input lot codes
 *   4. Shipping     → abbreviated headers, missing ship_to, mixed date formats
 *   5. Receiving    → missing immediate_previous_source, quantity mismatch, bad UOM
 *   6. Transformation → missing input TLCs, no transformation_date, inconsistent lot format
 *   7. First Land-Based Receiving → everything: bad dates, missing fields, duplicate, wrong CTE alias
 */

export interface SandboxSample {
  id: string;
  label: string;
  persona: string;
  cteType: string;
  messLevel: string;
  messDescription: string;
  csv: string;
}

export const SANDBOX_SAMPLES: SandboxSample[] = [
  // ── 1. Harvesting — Grower (mild mess) ────────────────────────────────────
  {
    id: "harvesting-grower",
    label: "Grower — Harvest Log",
    persona: "Sunrise Organic Farm",
    cteType: "harvesting",
    messLevel: "Low",
    messDescription: "Abbreviated units, non-standard date format",
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,harvest_date,field_name,harvester_business_name
harvesting,ORG-KALE-0401-001,Organic Curly Kale,1200,lb,Sunrise Organic Farm Watsonville CA,04/01/2026,North Field Block A,Sunrise Organic Farm LLC
harvesting,ORG-KALE-0401-002,Organic Curly Kale,800,lb.,Sunrise Organic Farm Watsonville CA,4/1/26,North Field Block B,Sunrise Organic Farm LLC
harvesting,ORG-SPIN-0401-001,Baby Spinach,2400,lbs,Sunrise Organic Farm Watsonville CA,2026-04-01,East Greenhouse 3,Sunrise Organic Farm LLC
harvesting,ORG-CHARD-0401-001,Rainbow Chard,600,Lbs,Sunrise Organic Farm Watsonville CA,April 1 2026,South Terrace,Sunrise Organic Farm LLC`,
  },

  // ── 2. Cooling — Cold Storage (moderate mess) ──────────────────────────────
  {
    id: "cooling-coldstorage",
    label: "Cold Storage — Cooling Records",
    persona: "Arctic Chain Cold Storage",
    cteType: "cooling",
    messLevel: "Low–Medium",
    messDescription: "Missing cooling date, inconsistent facility names",
    csv: `cte_type,lot_code,product,qty,uom,location,cooling_date,temperature
cooling,ORG-KALE-0401-001,Organic Curly Kale,1200,lbs,Arctic Chain Cold Storage Unit 7,2026-04-01,1.8
cooling,ORG-KALE-0401-002,Organic Curly Kale,800,lbs,Arctic Chain - Unit 7,2026-04-01,2.1
cooling,ORG-SPIN-0401-001,Baby Spinach,2400,lbs,ARCTIC CHAIN COLD STORAGE UNIT 7,,1.5
cooling,ORG-CHARD-0401-001,Rainbow Chard,600,lbs,Arctic Chain Unit7,2026-04-01,2.4`,
  },

  // ── 3. Packing — Packhouse (moderate mess) ─────────────────────────────────
  {
    id: "packing-packhouse",
    label: "Packhouse — Packing Log",
    persona: "Valley Fresh Packhouse",
    cteType: "initial_packing",
    messLevel: "Medium",
    messDescription: "Duplicate row, missing input lot codes on one entry",
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,packing_date,input_lot_codes
initial_packing,PKG-KALE-0402-001,Organic Kale 1lb Bag,1100,bags,Valley Fresh Packhouse,2026-04-02,ORG-KALE-0401-001
initial_packing,PKG-KALE-0402-001,Organic Kale 1lb Bag,1100,bags,Valley Fresh Packhouse,2026-04-02,ORG-KALE-0401-001
initial_packing,PKG-SPIN-0402-001,Baby Spinach 5oz Clamshell,4800,each,Valley Fresh Packhouse,2026-04-02,ORG-SPIN-0401-001
initial_packing,PKG-MIX-0402-001,Power Greens Mix 1lb,500,bag,Valley Fresh Packhouse,04/02/2026,`,
  },

  // ── 4. Shipping — Distributor (high mess) ──────────────────────────────────
  {
    id: "shipping-distributor",
    label: "Distributor — Shipping Manifest",
    persona: "FreshLine Distribution",
    cteType: "shipping",
    messLevel: "Medium–High",
    messDescription: "Missing destination, abbreviated headers, mixed date formats",
    csv: `type,tlc,product,qty,uom,ship_date,ship_from,ship_to,carrier,bol
shipping,PKG-KALE-0402-001,Organic Kale 1lb Bag,500,cases,2026-04-03,FreshLine DC Salinas,Metro Grocery Warehouse LA,Cold Express Logistics,BOL-20260403-001
shipping,PKG-KALE-0402-001,Organic Kale 1lb Bag,600,cs,04/03/2026,FreshLine DC Salinas,NorCal Foods Portland,Cold Express,BOL-20260403-002
shipping,PKG-SPIN-0402-001,Baby Spinach 5oz Clamshell,2400,each,4/3/26,FreshLine DC Salinas,,ColdEx,BOL-20260403-003
shipping,PKG-MIX-0402-001,Power Greens Mix 1lb,500,bags,April 3rd 2026,Freshline DC Salinas,Valley Organics SF,Cold Express Logistics,`,
  },

  // ── 5. Receiving — Retailer DC (high mess) ──────────────────────────────────
  {
    id: "receiving-retailer",
    label: "Retailer DC — Receiving Log",
    persona: "Metro Grocery Distribution",
    cteType: "receiving",
    messLevel: "High",
    messDescription: "Missing previous source, quantity mismatch, wrong UOM, no reference doc",
    csv: `event_type,batch_number,item_description,amount,unit,receive_date,receiving_location,immediate_previous_source,reference_document,temperature
receiving,PKG-KALE-0402-001,Organic Kale 1lb Bag,480,case,2026-04-04,Metro Grocery Warehouse LA,FreshLine Distribution,INV-88321,3.2
receiving,PKG-SPIN-0402-001,Baby Spinach 5oz,2400,EA,04/04/26,Metro Grocery whse LA,,PO-44210,4.1
receiving,PKG-MIX-0402-001,Power Greens Mix,500,bags,2026-04-04,Metro Grocery Warehouse LA,Freshline Dist.,,3.8
receiving,PKG-KALE-0402-001,Organic Kale 1lb Bag,600,cases,2026-04-04,NorCal Foods Recv Dock,FreshLine Distribution,INV-88322,2.9`,
  },

  // ── 6. Transformation — Processor (high mess) ──────────────────────────────
  {
    id: "transformation-processor",
    label: "Processor — Transformation Records",
    persona: "GreenLeaf Processing",
    cteType: "transformation",
    messLevel: "High",
    messDescription: "Missing input TLCs, no transformation date, inconsistent lot format",
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,transformation_date,input_lot_codes
transformation,GL-SALAD-0405-A,Premium Salad Kit 12oz,3000,units,GreenLeaf Processing Plant,2026-04-05,"PKG-KALE-0402-001,PKG-SPIN-0402-001"
transformation,GL-SALAD-0405-B,Caesar Salad Kit 10oz,1500,units,GreenLeaf Processing Plant,04/05/2026,PKG-KALE-0402-001
transformation,GL-WRAP-0405-A,Veggie Wrap Kit,800,each,Greenleaf Processing,,
transformation,GL_JUICE_0405_A,Green Juice 16oz,2000,bottles,GreenLeaf Processing Plant,2026-04-05,"PKG-SPIN-0402-001,PKG-MIX-0402-001"`,
  },

  // ── 7. First Land-Based Receiving — Seafood (extreme mess) ─────────────────
  {
    id: "flbr-seafood",
    label: "Seafood Dock — Landing Records",
    persona: "Pacific Coast Seafood",
    cteType: "first_land_based_receiving",
    messLevel: "Very High",
    messDescription: "Bad dates, missing fields, duplicate, wrong CTE alias, inconsistent everything",
    csv: `cte,lot,product,qty,uom,landing_date,location,previous_source,bol,temp
flbr,SAL-0401-DOCK4-001,Atlantic Salmon Fillets,2000,lb,2026-04-01,Pacific Seafood Dock 4 Portland OR,FV Ocean Harvest,BOL-2026-0401-042,-1.5
first_land_based_receiving,SAL-0401-DOCK4-001,Atlantic Salmon Fillets,2000,lbs,04/01/2026,Pacific Seafood - Dock 4,FV Ocean Harvest,BOL-2026-0401-042,-1.5
flbr,TUNA-0401-D2-001,Yellowfin Tuna Loin,800,pound,April 1st 2026,Pac Seafood Dock 2,,,-0.8
flbr,SHRMP-04O1-D4-001,Gulf Shrimp 16/20ct,1500,lbs,,Pacific Seafood Dock 4 Portland OR,FV Gulf Runner,BOL-2026-0401-043,
flbr,COD-0401-DOCK4-001,Pacific Cod Fillets,600,kg,2026/04/01,PACIFIC SEAFOOD DOCK 4,MV Northern Star,BOL-2026-0401-044,-2.1`,
  },

  // ── Bonus: Full Supply Chain (multi-CTE, shows trace-back) ────────────────
  {
    id: "full-chain",
    label: "Full Supply Chain — Farm to Store",
    persona: "End-to-End Example",
    cteType: "mixed",
    messLevel: "Mixed",
    messDescription: "Traces one lot from harvest to retail — messy data at every step",
    csv: `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,harvest_date,ship_date,ship_from_location,ship_to_location,receive_date,receiving_location,immediate_previous_source,reference_document,cooling_date,packing_date,input_lot_codes,transformation_date
harvesting,ROM-0410-F1-001,Romaine Lettuce Hearts,3000,lb,Coastline Farms Salinas CA,2026-04-10T06:00:00Z,04/10/2026,,,,,,,,,,
cooling,ROM-0410-F1-001,Romaine Lettuce Hearts,3000,lbs,Coastline Cooler #1,2026-04-10T09:00:00Z,,,,,,,,,,,,
shipping,ROM-0410-F1-001,Romaine Lettuce Hearts,3000,lbs,Coastline Farms DC,2026-04-10T14:00:00Z,,2026-04-10,Coastline Farms Salinas,FreshCo Distribution LA,,,,BOL-9910,,,,,
receiving,ROM-0410-F1-001,Romaine Lettuce,2950,lbs,FreshCo Distribution LA,2026-04-11T08:00:00Z,,,,,2026-04-11,FreshCo Dist. LA,Coastline Farms,INV-20261011,,,
transformation,CHOP-ROM-0411-001,Chopped Romaine 1lb Bag,2800,bags,FreshCo Processing,2026-04-11T12:00:00Z,,,,,,,,,,ROM-0410-F1-001,04/11/2026
shipping,CHOP-ROM-0411-001,Chopped Romaine 1lb bag,1400,bags,FreshCo Distribution LA,2026-04-12T06:00:00Z,,04/12/2026,FreshCo Dist LA,GreenMart Regional DC,,,,,,,
receiving,CHOP-ROM-0411-001,Chopped Romaine 1lb Bag,1380,bags,GreenMart Regional DC,2026-04-12T15:00:00Z,,,,,2026-04-12,GreenMart DC,FreshCo Distribution,PO-55123,,,`,
  },
];

/** The original simple 3-row sample, kept as the default */
export const SAMPLE_CSV_DEFAULT = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,harvest_date,reference_document,cooling_date,ship_date,ship_from_location,ship_to_location,tlc_source_reference,receive_date,receiving_location,immediate_previous_source
harvesting,LOT-2026-001,Romaine Lettuce,2000,lbs,Valley Fresh Farms,2026-03-12T08:00:00Z,2026-03-12,,,,,,,,,
shipping,LOT-2026-001,Romaine Lettuce,2000,lbs,Valley Fresh DC,2026-03-13T06:00:00Z,,BOL-4421,,,Valley Fresh Farms,FreshCo Distribution,Valley Fresh Farms LLC,,,
receiving,LOT-2026-001,Romaine Lettuce,1900,lbs,FreshCo Distribution,2026-03-13T14:00:00Z,,INV-8832,,,,,,2026-03-13,FreshCo DC East,Valley Fresh Farms LLC`;
