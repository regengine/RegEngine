"use client"

import * as React from "react"
import Link from "next/link"
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Callout } from "@/components/ui/callout"
import { Button } from "@/components/ui/button"
import { EmptyState, type EmptyStateProps } from "@/components/ui/empty-state"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

/**
 * DataTable — SPEC §4.
 *
 * Columns are a plain descriptor array rather than TanStack `ColumnDef`
 * generics: there is exactly one obvious implementation, which is what keeps
 * ten parallel page agents from diverging. TanStack Table stays available for
 * the couple of pages that already use its sorting/filtering machinery.
 *
 * `caption` is required and renders visually hidden, so every table has an
 * accessible name without an author having to remember one.
 */
export type DataTableColumn<T> = {
  key: string
  header: string
  /** Defaults to `String(row[key])`. */
  cell?: (row: T) => React.ReactNode
  align?: "left" | "right"
  /** Any CSS width, e.g. '12rem'. */
  width?: string
  /** Identifiers, hashes, timestamps. */
  mono?: boolean
  sortable?: boolean
}

export type DataTableSort = { key: string; direction: "asc" | "desc" }

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  data: T[]
  /** Visually hidden by default — the table's accessible name. */
  caption: string
  density?: "low" | "medium" | "high"
  toolbar?: {
    search?: { placeholder: string; value: string; onChange: (v: string) => void; label?: string }
    filters?: React.ReactNode
    actions?: React.ReactNode
  }
  status?: "idle" | "loading" | "error" | "empty"
  empty?: EmptyStateProps
  error?: { message: string; onRetry?: () => void }
  rowHref?: (row: T) => string | undefined
  rowKey?: (row: T, index: number) => string
  stickyHeader?: boolean
  /** Sticks the first column while the rest scrolls horizontally. */
  stickyFirstColumn?: boolean
  minWidth?: string
  sort?: DataTableSort
  onSortChange?: (sort: DataTableSort) => void
  pagination?: { page: number; pageSize: number; total: number; onPageChange: (p: number) => void }
  className?: string
}

const DENSITY_CELL = {
  low: "py-3.5",
  medium: "py-2.5",
  high: "py-1.5",
} as const

export function DataTable<T>({
  columns,
  data,
  caption,
  density = "medium",
  toolbar,
  status = "idle",
  empty,
  error,
  rowHref,
  rowKey,
  stickyHeader,
  stickyFirstColumn,
  minWidth = "560px",
  sort,
  onSortChange,
  pagination,
  className,
}: DataTableProps<T>) {
  const toggleSort = (key: string) => {
    if (!onSortChange) return
    const direction = sort?.key === key && sort.direction === "asc" ? "desc" : "asc"
    onSortChange({ key, direction })
  }

  const ariaSort = (key: string): React.AriaAttributes["aria-sort"] =>
    sort?.key === key ? (sort.direction === "asc" ? "ascending" : "descending") : "none"

  return (
    <div className={cn("rounded-lg border border-re-border bg-re-surface-card", className)}>
      {toolbar && (
        <div className="flex flex-wrap items-center gap-2 border-b border-re-border-subtle px-4 py-3">
          {toolbar.search && (
            <div className="w-full sm:w-64">
              <label htmlFor="data-table-search" className="sr-only">
                {toolbar.search.label ?? toolbar.search.placeholder}
              </label>
              <Input
                id="data-table-search"
                type="search"
                value={toolbar.search.value}
                placeholder={toolbar.search.placeholder}
                onChange={(e) => toolbar.search?.onChange(e.target.value)}
                leadingIcon={<Search />}
              />
            </div>
          )}
          {toolbar.filters}
          {toolbar.actions && <div className="ml-auto flex items-center gap-2">{toolbar.actions}</div>}
        </div>
      )}

      {status === "error" && error ? (
        <div className="p-4">
          <Callout
            tone="danger"
            role="alert"
            action={
              error.onRetry ? (
                <Button variant="secondary" size="sm" onClick={error.onRetry}>
                  Retry
                </Button>
              ) : undefined
            }
          >
            {error.message}
          </Callout>
        </div>
      ) : status === "loading" ? (
        <div className="space-y-2 p-4" aria-busy="true">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : status === "empty" || data.length === 0 ? (
        <EmptyState bare {...(empty ?? { title: "Nothing to show yet" })} />
      ) : (
        <div className="relative w-full overflow-x-auto">
          <table
            className="w-full caption-bottom text-ui tabular-nums"
            style={{ minWidth }}
          >
            <TableCaption className="sr-only">{caption}</TableCaption>
            <TableHeader>
              <TableRow>
                {columns.map((col, i) => (
                  <TableHead
                    key={col.key}
                    style={col.width ? { width: col.width } : undefined}
                    aria-sort={col.sortable ? ariaSort(col.key) : undefined}
                    className={cn(
                      col.align === "right" && "text-right",
                      stickyHeader && "sticky top-0 z-10",
                      stickyFirstColumn && i === 0 && "sticky left-0 z-20 bg-re-surface-inset"
                    )}
                  >
                    {col.sortable && onSortChange ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(col.key)}
                        className="inline-flex items-center gap-1 rounded-sm transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                      >
                        {col.header}
                        {sort?.key === col.key ? (
                          sort.direction === "asc" ? (
                            <ArrowUp className="h-3 w-3 text-re-text-primary" aria-hidden="true" />
                          ) : (
                            <ArrowDown className="h-3 w-3 text-re-text-primary" aria-hidden="true" />
                          )
                        ) : (
                          <ArrowUpDown className="h-3 w-3 text-re-text-muted" aria-hidden="true" />
                        )}
                      </button>
                    ) : (
                      col.header
                    )}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row, rowIndex) => {
                const href = rowHref?.(row)
                return (
                  <TableRow key={rowKey ? rowKey(row, rowIndex) : rowIndex}>
                    {columns.map((col, colIndex) => {
                      const content = col.cell
                        ? col.cell(row)
                        : String((row as Record<string, unknown>)[col.key] ?? "")
                      return (
                        <TableCell
                          key={col.key}
                          className={cn(
                            DENSITY_CELL[density],
                            col.align === "right" && "text-right",
                            col.mono && "font-mono text-[0.8125rem]",
                            stickyFirstColumn && colIndex === 0 && "sticky left-0 z-10 bg-re-surface-card"
                          )}
                        >
                          {href && colIndex === 0 ? (
                            <Link
                              href={href}
                              className="text-re-text-primary no-underline hover:text-re-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
                            >
                              {content}
                            </Link>
                          ) : (
                            content
                          )}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                )
              })}
            </TableBody>
          </table>
        </div>
      )}

      {pagination && status === "idle" && data.length > 0 && (
        <div className="flex items-center justify-between border-t border-re-border-subtle px-4 py-2 text-small text-re-text-tertiary">
          <span>
            {(pagination.page - 1) * pagination.pageSize + 1}–
            {Math.min(pagination.page * pagination.pageSize, pagination.total)} of {pagination.total}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={pagination.page <= 1}
              onClick={() => pagination.onPageChange(pagination.page - 1)}
            >
              Previous
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={pagination.page * pagination.pageSize >= pagination.total}
              onClick={() => pagination.onPageChange(pagination.page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow }
