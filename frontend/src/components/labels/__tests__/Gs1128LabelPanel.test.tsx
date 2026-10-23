import { render, screen } from "@testing-library/react"

import { Gs1128LabelPanel } from "@/components/labels/Gs1128LabelPanel"

describe("Gs1128LabelPanel", () => {
  it("renders an empty state when no elements are passed", () => {
    render(<Gs1128LabelPanel />)

    expect(screen.getByText("No label data yet")).toBeInTheDocument()
    expect(screen.getByText(/ingest real GTIN and lot data/i)).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("renders an empty state for an empty element list", () => {
    render(<Gs1128LabelPanel elements={[]} />)

    expect(screen.getByText("No label data yet")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })
})
