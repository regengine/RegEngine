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

  it("labels the demo checklist and advisory checks", () => {
    render(<HomePage />);

    expect(screen.getByText("What the export checklist still flags")).toBeInTheDocument();
    expect(screen.getAllByText("FreshPack Central").length).toBeGreaterThan(0);
    expect(screen.getByText("Export checklist (advisory)")).toBeInTheDocument();
    expect(screen.getAllByText("Hash verified").length).toBeGreaterThan(0);
  });

  it("uses compliance-specific metrics instead of generic SaaS proof", () => {
    render(<HomePage />);

    expect(screen.getByText("Demo workspace · synthetic data · 3 open checklist items")).toBeInTheDocument();
    expect(screen.getByText("FTL list overlap")).toBeInTheDocument();
    expect(screen.getByText("KDE completeness")).toBeInTheDocument();
    expect(screen.getByText("Export checklist")).toBeInTheDocument();
    expect(screen.queryByText(/save time/i)).not.toBeInTheDocument();
  });
});
