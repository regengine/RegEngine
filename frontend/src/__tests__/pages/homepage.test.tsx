import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";

describe("HomePage Compliance OS foundation", () => {
  it("leads with compliance operating system positioning", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", {
        name: "FSMA 204 recordkeeping for the Food Traceability Rule.",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/send records by csv upload or the json events api\. epcis 2\.0 is in preview\./i),
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
