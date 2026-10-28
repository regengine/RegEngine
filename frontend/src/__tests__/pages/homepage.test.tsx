import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";

describe("HomePage Compliance OS foundation", () => {
  it("leads with compliance operating system positioning", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", {
        name: "Find the gaps in your suppliers' traceability data before a buyer or the FDA does.",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/csv uploads and a json events api\. epcis 2\.0 is in preview\./i),
    ).toBeInTheDocument();
  });

  it("offers one clear next step and labels the example report as example data", () => {
    render(<HomePage />);

    expect(screen.getAllByRole("link", { name: /send us one supplier file/i })[0]).toHaveAttribute("href", "/contact");
    expect(screen.getByText("Example data")).toBeInTheDocument();
  });

  it("keeps the enforcement date and the limits of the claims on the page", () => {
    const { container } = render(<HomePage />);
    const text = container.textContent ?? "";

    expect(text).toContain("July 20, 2028");
    expect(text).toContain("What this is not");
    expect(text).toContain("Not FDA endorsement");
  });

  it("contains no synthetic demo data", () => {
    const { container } = render(<HomePage />);
    const text = container.textContent ?? "";

    expect(text).not.toMatch(/synthetic/i);
    expect(text).not.toMatch(/demo workspace/i);
    expect(text).not.toContain("RE-DEMO-PKG");
    expect(text).not.toMatch(/FreshPack Central|Valley Farms|Cold Dock 7/);
  });
});
