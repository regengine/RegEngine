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

    it("includes provided filters with an exact query string", () => {
        const lot = "seg";
        const start = "d0";
        const end = "d1";
        const query = buildDemoExportQuery({
            preset: "all_records",
            traceabilityLotCode: lot,
            startDate: start,
            endDate: end,
        });
        expect(query).toBe(
            `?preset=all_records&traceability_lot_code=${encodeURIComponent(lot)}&start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`,
        );
    });

    it("omits whitespace-only lots and preserves nonblank padding exactly", () => {
        expect(
            buildDemoExportQuery({
                preset: "all_records",
                traceabilityLotCode: "   ",
            }),
        ).toBe("?preset=all_records");
        const lot = "  padded  ";
        const query = buildDemoExportQuery({ traceabilityLotCode: lot });
        const expected = new URLSearchParams();
        expected.set("traceability_lot_code", lot);
        expect(query).toBe(`?${expected.toString()}`);
        const params = new URLSearchParams(query.slice(1));
        expect(params.get("traceability_lot_code")).toBe(lot);
    });
});
