"use client"

import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"

export interface Gs1LabelElement {
  ai: string
  value: string
}

export interface Gs1128LabelPanelProps {
  elements?: readonly Gs1LabelElement[] | null
  onDownloadPdf?: (elements: readonly Gs1LabelElement[]) => void
  onDownloadZpl?: (elements: readonly Gs1LabelElement[]) => void
}

/**
 * Presentational GS1-128 label actions. Callers pass ingested elements.
 * An empty list stays empty: this component never invents identifier text.
 */
export function Gs1128LabelPanel({
  elements,
  onDownloadPdf,
  onDownloadZpl,
}: Gs1128LabelPanelProps) {
  if (!elements || elements.length === 0) {
    return (
      <EmptyState
        title="No label data yet"
        description="Ingest real GTIN and lot data to generate a GS1-128 label."
      />
    )
  }

  return (
    <section className="flex flex-col gap-4" aria-label="GS1-128 label">
      <ul className="flex flex-col gap-1 text-ui text-re-text-primary">
        {elements.map((element, index) => (
          <li key={`${element.ai}-${index}`}>
            <span className="text-re-text-tertiary">({element.ai})</span> {element.value}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => onDownloadPdf?.(elements)}>
          Download PDF
        </Button>
        <Button type="button" variant="secondary" onClick={() => onDownloadZpl?.(elements)}>
          Download ZPL
        </Button>
      </div>
    </section>
  )
}
