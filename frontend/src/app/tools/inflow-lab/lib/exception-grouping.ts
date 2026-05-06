export type ExceptionPatternId = "handoff" | "source" | "mixed";

export type LotForGrouping = {
    lotCode: string;
    product: string;
    missingCtes: string[];
    readiness: {
        state: "ready" | "warning" | "blocked";
        deliveryLabel: string;
        exportReady: boolean;
    };
    events?: number;
    cases?: number;
    supplier?: string;
};

export type ExceptionGroup<TLot extends LotForGrouping = LotForGrouping> = {
    id: ExceptionPatternId;
    label: string;
    description: string;
    owner: string;
    bulkActionable: boolean;
    lots: TLot[];
};

const HANDOFF_LABELS = new Set(["Initial packing", "Shipping", "DC receiving"]);
const SOURCE_LABELS = new Set(["Harvesting", "Cooling"]);

export function classifyExceptionLot(lot: LotForGrouping): ExceptionPatternId {
    const missing = lot.missingCtes;
    const hasHandoff = missing.some((cte) => HANDOFF_LABELS.has(cte));
    const hasSource = missing.some((cte) => SOURCE_LABELS.has(cte));

    if (hasHandoff && hasSource) return "mixed";
    if (hasHandoff && !hasSource) return "handoff";
    if (hasSource && !hasHandoff) return "source";
    return "mixed";
}

export function groupExceptionsByPattern<TLot extends LotForGrouping>(
    lots: TLot[]
): ExceptionGroup<TLot>[] {
    const handoff: TLot[] = [];
    const source: TLot[] = [];
    const mixed: TLot[] = [];

    for (const lot of lots) {
        const pattern = classifyExceptionLot(lot);
        if (pattern === "handoff") handoff.push(lot);
        else if (pattern === "source") source.push(lot);
        else mixed.push(lot);
    }

    return [
        {
            id: "handoff",
            label: "Missing handoff evidence",
            description: "Initial packing, shipping, DC receiving — handoff fields absent.",
            owner: "Shipping / receiving source",
            bulkActionable: handoff.length > 0,
            lots: handoff,
        },
        {
            id: "source",
            label: "Missing source evidence",
            description: "Harvesting and cooling KDEs absent at the source.",
            owner: "Supplier data owner",
            bulkActionable: source.length > 0,
            lots: source,
        },
        {
            id: "mixed",
            label: "Mixed / multi-cause",
            description: "Combinations across handoff and source. Treat individually.",
            owner: "Mixed",
            bulkActionable: false,
            lots: mixed,
        },
    ];
}

export type SourceSupplierBreakdown = {
    harvestSuppliers: { supplier: string; lotCount: number }[];
    coolingSuppliers: { supplier: string; lotCount: number }[];
    overlapCount: number;
};

export function summarizeSourceSuppliers(
    sourceLots: LotForGrouping[]
): SourceSupplierBreakdown {
    const harvestBySupplier = new Map<string, number>();
    const coolingBySupplier = new Map<string, number>();
    let overlap = 0;

    for (const lot of sourceLots) {
        const supplier = lot.supplier ?? "Unknown supplier";
        const missingHarvest = lot.missingCtes.includes("Harvesting");
        const missingCooling = lot.missingCtes.includes("Cooling");
        if (missingHarvest) {
            harvestBySupplier.set(supplier, (harvestBySupplier.get(supplier) ?? 0) + 1);
        }
        if (missingCooling) {
            coolingBySupplier.set(supplier, (coolingBySupplier.get(supplier) ?? 0) + 1);
        }
        if (missingHarvest && missingCooling) {
            overlap += 1;
        }
    }

    return {
        harvestSuppliers: Array.from(harvestBySupplier, ([supplier, lotCount]) => ({
            supplier,
            lotCount,
        })),
        coolingSuppliers: Array.from(coolingBySupplier, ([supplier, lotCount]) => ({
            supplier,
            lotCount,
        })),
        overlapCount: overlap,
    };
}
