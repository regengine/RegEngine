import { describe, expect, it } from "vitest";
import {
  complianceRouteFamilies,
  getComplianceStateStyle,
  getRouteFamilyForPath,
} from "@/lib/compliance-os";

describe("Compliance OS state model", () => {
  it("maps object states to visible labels and semantic tokens", () => {
    expect(getComplianceStateStyle("blocked")).toMatchObject({
      label: "Blocked",
      tone: "calm-urgency",
      colorVar: "var(--re-danger)",
    });

    expect(getComplianceStateStyle("committed")).toMatchObject({
      label: "Committed",
      tone: "trust",
      colorVar: "var(--re-evidence)",
    });
  });
});

describe("Compliance OS route taxonomy", () => {
  it("keeps marketing routes on the command-center shell", () => {
    expect(getRouteFamilyForPath("/")).toBe(complianceRouteFamilies.marketing);
    expect(getRouteFamilyForPath("/product")).toMatchObject({
      label: "Marketing",
      shell: "Command Center first viewport",
    });
  });

  it("resolves nested routes to the correct family by prefix", () => {
    expect(getRouteFamilyForPath("/tools/inflow-lab")).toMatchObject({
      label: "Tools",
      shell: "Food Operations Workbench",
    });
    expect(getRouteFamilyForPath("/docs/api")).toMatchObject({
      label: "Developer docs",
      density: "high",
    });
    expect(getRouteFamilyForPath("/dashboard/suppliers")).toMatchObject({
      label: "App and dashboard",
      shell: "Readiness Flight Deck",
    });
  });
});
