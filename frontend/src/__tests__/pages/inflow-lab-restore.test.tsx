import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactElement } from "react";

vi.mock("next/navigation", () => ({
    notFound: vi.fn(() => {
        throw new Error("notFound");
    }),
}));

vi.mock("@/components/experimental/FeatureNotEnabled", () => ({
    FeatureNotEnabled: ({ featureName }: { featureName: string }) => (
        <div>{`feature-disabled:${featureName}`}</div>
    ),
}));

vi.mock("@/app/tools/inflow-lab/components/InflowLabClient", () => ({
    InflowLabClient: () => <div>inflow-lab-client</div>,
}));

describe("Inflow Lab tools page restore", () => {
    beforeEach(() => {
        vi.resetModules();
        vi.unstubAllEnvs();
    });

    afterEach(() => {
        vi.unstubAllEnvs();
    });

    it("renders the client when the per-tool experimental flag is on", async () => {
        vi.stubEnv("NEXT_PUBLIC_ENABLED_EXPERIMENTAL_TOOLS", "inflow-lab");
        const { default: InflowLabPage } = await import("@/app/tools/inflow-lab/page");
        expect(renderToStaticMarkup(InflowLabPage() as ReactElement)).toContain("inflow-lab-client");
    });

    it("shows FeatureNotEnabled when the tool flag is off, instead of hard notFound", async () => {
        vi.stubEnv("NEXT_PUBLIC_ENABLED_EXPERIMENTAL_TOOLS", "");
        vi.stubEnv("NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES", "");
        const { default: InflowLabPage } = await import("@/app/tools/inflow-lab/page");
        expect(renderToStaticMarkup(InflowLabPage() as ReactElement)).toContain(
            "feature-disabled:Inflow Lab",
        );
    });
});
