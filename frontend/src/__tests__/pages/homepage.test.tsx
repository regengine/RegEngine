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

  it("shows a No data yet empty state instead of a synthetic workspace", () => {
    render(<HomePage />);

    expect(screen.getByText("No data yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start setup/i })).toHaveAttribute("href", "/signup");
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
