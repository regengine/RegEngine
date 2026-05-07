import { describe, it, expect } from "vitest";

import {
    classifyExceptionLot,
    groupExceptionsByPattern,
    summarizeSourceSuppliers,
    type LotForGrouping,
} from "@/app/tools/inflow-lab/lib/exception-grouping";

function lot(id: string, missingCtes: string[], opts: Partial<LotForGrouping> = {}): LotForGrouping {
    return {
        lotCode: id,
        product: opts.product ?? "Romaine",
        missingCtes,
        readiness: opts.readiness ?? {
            state: "warning",
            deliveryLabel: "posted",
            exportReady: false,
        },
        events: opts.events ?? 4,
        cases: opts.cases ?? 4,
        supplier: opts.supplier,
    };
}

function buildHandoffLots(count: number): LotForGrouping[] {
    return Array.from({ length: count }, (_, i) => {
        const missing = i % 3 === 0 ? ["Shipping"] : i % 3 === 1 ? ["Initial packing"] : ["DC receiving"];
        return lot(`TLC-HANDOFF-${i.toString().padStart(3, "0")}`, missing, { product: "Romaine" });
    });
}

function buildSourceLots(count: number, supplierSplit: { harvestSupplier: string; coolingSupplier: string }) {
    return Array.from({ length: count }, (_, i) => {
        const role = i % 5;
        if (role === 0 || role === 1 || role === 2) {
            return lot(`TLC-SOURCE-H-${i}`, ["Harvesting"], { supplier: supplierSplit.harvestSupplier });
        }
        if (role === 3) {
            return lot(`TLC-SOURCE-C-${i}`, ["Cooling"], { supplier: supplierSplit.coolingSupplier });
        }
        return lot(`TLC-SOURCE-B-${i}`, ["Harvesting", "Cooling"], { supplier: supplierSplit.harvestSupplier });
    });
}

function buildMixedLots(count: number) {
    return Array.from({ length: count }, (_, i) => {
        const combos = [
            ["Harvesting", "Shipping"],
            ["Cooling", "DC receiving"],
            ["Initial packing", "Harvesting"],
            ["Shipping", "Cooling"],
        ];
        return lot(`TLC-MIXED-${i}`, combos[i % combos.length]);
    });
}

describe("classifyExceptionLot", () => {
    it("classifies a lot with only handoff CTEs missing as handoff", () => {
        expect(classifyExceptionLot(lot("a", ["Shipping"]))).toBe("handoff");
        expect(classifyExceptionLot(lot("a", ["Initial packing", "DC receiving"]))).toBe("handoff");
    });

    it("classifies a lot with only source CTEs missing as source", () => {
        expect(classifyExceptionLot(lot("a", ["Harvesting"]))).toBe("source");
        expect(classifyExceptionLot(lot("a", ["Harvesting", "Cooling"]))).toBe("source");
    });

    it("classifies a lot with both handoff and source CTEs missing as mixed", () => {
        expect(classifyExceptionLot(lot("a", ["Harvesting", "Shipping"]))).toBe("mixed");
        expect(classifyExceptionLot(lot("a", ["Cooling", "DC receiving"]))).toBe("mixed");
    });

    it("classifies a lot with no missing CTEs but otherwise blocked as mixed", () => {
        expect(classifyExceptionLot(lot("a", []))).toBe("mixed");
    });
});

describe("groupExceptionsByPattern", () => {
    it("returns three groups in canonical order: handoff, source, mixed", () => {
        const groups = groupExceptionsByPattern([]);
        expect(groups.map((g) => g.id)).toEqual(["handoff", "source", "mixed"]);
    });

    it("partitions a 35-lot fixture into the right counts (18 / 10 / 7)", () => {
        const fixture: LotForGrouping[] = [
            ...buildHandoffLots(18),
            ...buildSourceLots(10, { harvestSupplier: "Supplier B", coolingSupplier: "Supplier C" }),
            ...buildMixedLots(7),
        ];
        expect(fixture).toHaveLength(35);

        const groups = groupExceptionsByPattern(fixture);

        const byId = Object.fromEntries(groups.map((g) => [g.id, g]));
        expect(byId.handoff.lots).toHaveLength(18);
        expect(byId.source.lots).toHaveLength(10);
        expect(byId.mixed.lots).toHaveLength(7);
    });

    it("flags handoff and source groups as bulk-actionable but mixed as not", () => {
        const fixture: LotForGrouping[] = [
            ...buildHandoffLots(2),
            ...buildSourceLots(2, { harvestSupplier: "Supplier B", coolingSupplier: "Supplier C" }),
            ...buildMixedLots(2),
        ];

        const groups = groupExceptionsByPattern(fixture);
        const byId = Object.fromEntries(groups.map((g) => [g.id, g]));

        expect(byId.handoff.bulkActionable).toBe(true);
        expect(byId.source.bulkActionable).toBe(true);
        expect(byId.mixed.bulkActionable).toBe(false);
    });

    it("preserves lot identity within each group (no reordering across groups)", () => {
        const handoffLot = lot("HO-1", ["Shipping"]);
        const sourceLot = lot("SR-1", ["Harvesting"]);
        const mixedLot = lot("MX-1", ["Harvesting", "Shipping"]);

        const groups = groupExceptionsByPattern([mixedLot, sourceLot, handoffLot]);
        const byId = Object.fromEntries(groups.map((g) => [g.id, g]));

        expect(byId.handoff.lots[0].lotCode).toBe("HO-1");
        expect(byId.source.lots[0].lotCode).toBe("SR-1");
        expect(byId.mixed.lots[0].lotCode).toBe("MX-1");
    });
});

describe("summarizeSourceSuppliers", () => {
    it("breaks source lots down by supplier and missing-KDE field with overlap", () => {
        const sourceLots: LotForGrouping[] = [
            ...Array.from({ length: 4 }, (_, i) =>
                lot(`B-${i}`, ["Harvesting"], { supplier: "Supplier B" })
            ),
            ...Array.from({ length: 2 }, (_, i) =>
                lot(`C-${i}`, ["Cooling"], { supplier: "Supplier C" })
            ),
            ...Array.from({ length: 4 }, (_, i) =>
                lot(`BC-${i}`, ["Harvesting", "Cooling"], { supplier: "Supplier B" })
            ),
        ];

        const summary = summarizeSourceSuppliers(sourceLots);
        const harvestB = summary.harvestSuppliers.find((s) => s.supplier === "Supplier B");
        const coolingC = summary.coolingSuppliers.find((s) => s.supplier === "Supplier C");

        expect(harvestB?.lotCount).toBe(8);
        expect(coolingC?.lotCount).toBe(2);
        expect(summary.overlapCount).toBe(4);
    });
});
