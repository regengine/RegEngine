import { describe, expect, it } from "vitest";
import { buildDemoExportQuery } from "./demo-export-query";

describe("buildDemoExportQuery", () => {
    it("omits empty lot and date filters so defaults cover all demo events", () => {
        const query = buildDemoExportQuery({
            preset: "all_records",
            traceabilityLotCode: "",
            startDate: "",
            endDate: "",
        });
        expect(query).toBe("?preset=all_records");
        expect(query.includes("traceability_lot_code")).toBe(false);
        expect(query.includes("start_date")).toBe(false);
        expect(query.includes("end_date")).toBe(false);
    });

    it("returns an empty string when every filter is blank", () => {
        expect(buildDemoExportQuery({})).toBe("");
        expect(
            buildDemoExportQuery({
                preset: "   ",
                traceabilityLotCode: "",
                startDate: "",
                endDate: undefined,
            }),
        ).toBe("");
    });

    it("includes provided filters by shape without inventing lot or date values", () => {
        const lot = "seg";
        const start = "d0";
        const end = "d1";
        const query = buildDemoExportQuery({
            preset: "all_records",
            traceabilityLotCode: lot,
            startDate: start,
            endDate: end,
        });
        expect(query.startsWith("?")).toBe(true);
        expect(query).toContain("preset=all_records");
        expect(query).toContain(`traceability_lot_code=${lot}`);
        expect(query).toContain(`start_date=${start}`);
        expect(query).toContain(`end_date=${end}`);
    });

    it("preserves nonblank lot codes without trimming", () => {
        const lot = "  padded  ";
        const query = buildDemoExportQuery({ traceabilityLotCode: lot });
        expect(query).toContain("traceability_lot_code=");
        const params = new URLSearchParams(query.slice(1));
        expect(params.get("traceability_lot_code")).toBe(lot);
    });
});
