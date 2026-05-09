import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";

describe("HomePage Compliance OS foundation", () => {
  it("leads with compliance operating system positioning", () => {
    render(<HomePage />);

    // Per PR #2206: hero rewritten — H1 is now "FSMA 204 traceability evidence layer."
    // and the supporting copy describes the ingest → preflight → audit → export flow.
    expect(
      screen.getByRole("heading", {
        name: "FSMA 204 traceability evidence layer.",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/ingest supply-chain data through webhooks, csv, epcis, or edi/i),
    ).toBeInTheDocument();
  });

  it("renders proof modules in the first viewport", () => {
    render(<HomePage />);

    expect(screen.getByText("Traceability readiness")).toBeInTheDocument();
    expect(screen.getAllByText("Supplier Gap Radar").length).toBeGreaterThan(0);
    expect(screen.getByText("Export eligibility gate")).toBeInTheDocument();
    expect(screen.getAllByText("Hash verified").length).toBeGreaterThan(0);
  });

  it("uses compliance-specific metrics instead of generic SaaS proof", () => {
    render(<HomePage />);

    expect(screen.getByText("Demo workspace · sample data")).toBeInTheDocument();
    expect(screen.getByText("FTL coverage")).toBeInTheDocument();
    expect(screen.getByText("KDE completeness")).toBeInTheDocument();
    expect(screen.getByText("Records with full provenance")).toBeInTheDocument();
    expect(screen.queryByText(/save time/i)).not.toBeInTheDocument();
  });
});
