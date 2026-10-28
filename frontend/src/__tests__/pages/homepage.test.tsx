import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";
import { capabilities } from "@/lib/capabilities";

describe("HomePage", () => {
  it("leads with the records request hook and the live ingest paths", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", {
        name: "The Food Traceability Rule lets the FDA ask for a sortable spreadsheet within 24 hours. Supplier data does not arrive that way.",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/send records by csv upload or the json events api\. epcis 2\.0 is in preview\./i),
    ).toBeInTheDocument();
  });

  it("sends the primary call to action to the free file check", () => {
    render(<HomePage />);

    expect(screen.getByRole("link", { name: /^check a supplier file$/i })).toHaveAttribute("href", "/tools/data-import");
    expect(screen.getByRole("link", { name: /open the verifier/i })).toHaveAttribute("href", "/verify");
  });

  it("lists ingest paths from the capabilities registry instead of a workspace mock", () => {
    render(<HomePage />);

    for (const name of capabilities.live) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    for (const name of capabilities.preview) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
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
