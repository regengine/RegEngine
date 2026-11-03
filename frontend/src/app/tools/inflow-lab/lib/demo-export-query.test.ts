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

    it("trims lot values and omits whitespace-only lots so spaces never become +++", () => {
        // Spaces-only must not emit traceability_lot_code=+++.
        expect(
            buildDemoExportQuery({
                preset: "all_records",
                traceabilityLotCode: "   ",
            }),
        ).toBe("?preset=all_records");
        expect(buildDemoExportQuery({ traceabilityLotCode: " \t " })).toBe("");

        const query = buildDemoExportQuery({
            traceabilityLotCode: "  seg  ",
        });
        expect(query).toBe("?traceability_lot_code=seg");
        const params = new URLSearchParams(query.slice(1));
        expect(params.get("traceability_lot_code")).toBe("seg");
    });
});
