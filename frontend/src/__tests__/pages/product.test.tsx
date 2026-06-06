import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ProductPage from "@/app/product/page";

describe("ProductPage Inflow impact illustration", () => {
  it("shows how Inflow changes what RegEngine can persist and export", () => {
    render(<ProductPage />);

    expect(
      screen.getByRole("heading", {
        name: "A workbench for deciding what can become evidence.",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Inflow affects RegEngine before evidence exists")).toBeInTheDocument();
    expect(screen.getByText("Raw supplier feed")).toBeInTheDocument();
    expect(screen.getByText(/readiness score, fix queue, and commit gate state/i)).toBeInTheDocument();

    for (const stage of ["Normalize", "Score", "Route", "Gate"]) {
      expect(screen.getByRole("heading", { name: stage })).toBeInTheDocument();
    }

    expect(screen.getByRole("heading", { name: "Fix before evidence" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Persist and prove" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tenant-scoped evidence" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Export-ready package" })).toBeInTheDocument();
  });
});
