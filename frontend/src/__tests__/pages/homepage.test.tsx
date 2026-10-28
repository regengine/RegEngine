import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";
import { capabilities } from "@/lib/capabilities";

describe("HomePage", () => {
  it("leads with the records request hook and the live ingest paths", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", {
        name: "In an outbreak or recall, the Food Traceability Rule lets the FDA ask for a sortable spreadsheet due within 24 hours. Supplier data does not arrive that way.",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/send records by csv upload or the json events api\. epcis 2\.0 is in preview\./i),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText(/21 CFR 1\.1455\(c\)\(3\)\(ii\)/)).toBeInTheDocument();
    expect(screen.getByText(/does not imply FDA endorsement or certification/i)).toBeInTheDocument();
  });

  it("sends the primary call to action to a free tool that works without an API key", () => {
    render(<HomePage />);

    // identical destinations carry identical accessible names (hero and next steps)
    const checklistLinks = screen.getAllByRole("link", { name: /^see the fields your records need$/i });
    expect(checklistLinks).toHaveLength(2);
    for (const link of checklistLinks) expect(link).toHaveAttribute("href", "/tools/kde-checker");
    const verifyLinks = screen.getAllByRole("link", { name: /^verify an evidence bundle$/i });
    expect(verifyLinks).toHaveLength(2);
    for (const link of verifyLinks) expect(link).toHaveAttribute("href", "/verify");
    expect(screen.getByText(/no account, no api key/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /check a supplier file/i })).not.toBeInTheDocument();
  });

  it("lists ingest paths from the capabilities registry, each under its own status", () => {
    const { container } = render(<HomePage />);

    expect(capabilities.live.length).toBeGreaterThan(0);
    expect(capabilities.preview.length).toBeGreaterThan(0);

    const liveList = screen.getByRole("heading", { name: "Live", level: 3 }).nextElementSibling as HTMLElement;
    const previewList = screen.getByRole("heading", { name: "Preview", level: 3 }).nextElementSibling as HTMLElement;
    for (const name of capabilities.live) {
      expect(within(liveList).getByText(name)).toBeInTheDocument();
      expect(within(previewList).queryByText(name)).not.toBeInTheDocument();
    }
    for (const name of capabilities.preview) {
      expect(within(previewList).getByText(name)).toBeInTheDocument();
      expect(within(liveList).queryByText(name)).not.toBeInTheDocument();
    }
    // every preview row carries a Preview badge; live rows carry none
    expect(within(previewList).getAllByText("Preview")).toHaveLength(capabilities.preview.length);
    expect(within(liveList).queryByText("Preview")).not.toBeInTheDocument();

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bEDI\b|\bSFTP\b/);
    expect(screen.queryByText("No data yet")).not.toBeInTheDocument();
  });

  it("does not say pre-revenue and contains no invented data", () => {
    const { container } = render(<HomePage />);
    const text = container.textContent ?? "";

    expect(text).not.toMatch(/pre-revenue/i);
    expect(text).not.toMatch(/synthetic/i);
    expect(text).not.toMatch(/demo workspace/i);
    expect(text).not.toContain("RE-DEMO-PKG");
    expect(text).not.toMatch(/FreshPack Central|Valley Farms|Cold Dock 7/);
  });
});
