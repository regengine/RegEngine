import { describe, expect, it } from "vitest";
import { buildDemoExportQuery } from "./demo-export-query";

describe("buildDemoExportQuery", () => {
    it("omits empty lot and date filters so defaults cover all demo events", () => {
        expect(
            buildDemoExportQuery({
                preset: "all_records",
                traceabilityLotCode: "",
                startDate: "",
                endDate: "",
            }),
        ).toBe("?preset=all_records");
    });

    it("returns an empty string when every filter is blank", () => {
        expect(buildDemoExportQuery({})).toBe("");
        expect(
            buildDemoExportQuery({
                preset: "   ",
                traceabilityLotCode: "  ",
                startDate: "",
                endDate: undefined,
            }),
        ).toBe("");
    });

    it("includes only provided lot and date filters", () => {
        expect(
            buildDemoExportQuery({
                preset: "all_records",
                traceabilityLotCode: "LOT-1",
                startDate: "2026-07-01",
                endDate: "2026-07-31",
            }),
        ).toBe(
            "?preset=all_records&traceability_lot_code=LOT-1&start_date=2026-07-01&end_date=2026-07-31",
        );
    });
});
