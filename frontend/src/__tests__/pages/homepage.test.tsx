import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";
import { capabilities } from "@/lib/capabilities";

describe("HomePage", () => {
  it("leads with the records request hook and the disclaimer", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "Find the gaps before the FDA does.", level: 1 })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText(/21 CFR 1\.1455\(c\)\(3\)\(ii\)/)).toBeInTheDocument();
    const disclaimer = screen.getByText(/does not imply FDA endorsement or certification/i).textContent ?? "";
    for (const clause of [
      "not a readiness score",
      "does not claim that any workspace meets the 24-hour request",
      "not a recall clock product",
      "shows no live customer metrics",
      "not legal advice",
    ]) {
      expect(disclaimer).toContain(clause);
    }
    expect(disclaimer).toMatch(/Live today: CSV upload and JSON events API\./);
    expect(disclaimer).toMatch(/In preview: EPCIS 2\.0 intake and export\./);
  });

  it("sends the primary call to action to a free tool and the secondary one to the public workspace", () => {
    render(<HomePage />);

    // identical destinations carry identical accessible names (hero and free tools)
    const checklistLinks = screen.getAllByRole("link", { name: /^see the fields your records need/i });
    expect(checklistLinks).toHaveLength(2);
    for (const link of checklistLinks) expect(link).toHaveAttribute("href", "/tools/kde-checker");
    const verifyLinks = screen.getAllByRole("link", { name: /^verify an evidence bundle/i });
    expect(verifyLinks).toHaveLength(1);
    for (const link of verifyLinks) expect(link).toHaveAttribute("href", "/verify");
    const demoLinks = screen.getAllByRole("link", { name: /demo workspace/i });
    expect(demoLinks.length).toBeGreaterThanOrEqual(2);
    for (const link of demoLinks) expect(link).toHaveAttribute("href", "/demo");
    expect(screen.getByRole("link", { name: /book a 30-min call/i })).toHaveAttribute("href", "/contact");
    expect(screen.getAllByText(/no account needed/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /check a supplier file/i })).not.toBeInTheDocument();
  });

  it("renders the hero workbench with one open gap per chain", () => {
    render(<HomePage />);

    expect(screen.getByRole("tablist", { name: /ftl food/i })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(5);
    expect(screen.getByText(/one record is missing a required field/i)).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
    expect(screen.getByText("Needs correction")).toBeInTheDocument();
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

  it("does not say pre-revenue and contains no retired invented data", () => {
    const { container } = render(<HomePage />);
    const text = container.textContent ?? "";

    expect(text).not.toMatch(/pre-revenue/i);
    expect(text).not.toContain("RE-DEMO-PKG");
    expect(text).not.toMatch(/FreshPack Central|Valley Farms|Cold Dock 7/);
    expect(text).not.toMatch(/sandbox/i);
  });
});
