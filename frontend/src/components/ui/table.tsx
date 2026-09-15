import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Table — SPEC §4. The single table primitive; `.re-rule-table` and
 * `.re-workbench-table` remain as CSS aliases of this recipe for legacy markup.
 *
 * At narrow widths a table stays a table inside a horizontal scroller with a
 * sticky first column. Cards-instead-of-rows is deliberately not used:
 * operators scan columns, and swapping <table> for <ul> below a breakpoint
 * changes the DOM role and breaks role-based assertions.
 */
const Table = React.forwardRef<
    HTMLTableElement,
    React.HTMLAttributes<HTMLTableElement>
>(({ className, ...props }, ref) => (
    <div className="relative w-full overflow-x-auto">
        <table
            ref={ref}
            className={cn("w-full caption-bottom text-ui tabular-nums", className)}
            {...props}
        />
    </div>
))
Table.displayName = "Table"

const TableHeader = React.forwardRef<
    HTMLTableSectionElement,
    React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
    <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
))
TableHeader.displayName = "TableHeader"

const TableBody = React.forwardRef<
    HTMLTableSectionElement,
    React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
))
TableBody.displayName = "TableBody"

const TableFooter = React.forwardRef<
    HTMLTableSectionElement,
    React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
    <tfoot
        ref={ref}
        className={cn(
            "border-t border-re-border-subtle bg-re-surface-inset font-medium [&>tr]:last:border-b-0",
            className
        )}
        {...props}
    />
))
TableFooter.displayName = "TableFooter"

const TableRow = React.forwardRef<
    HTMLTableRowElement,
    React.HTMLAttributes<HTMLTableRowElement>
>(({ className, ...props }, ref) => (
    <tr
        ref={ref}
        className={cn(
            "border-b border-re-border-subtle transition-colors duration-120 last:border-0 hover:bg-re-surface-inset/60 focus-within:bg-re-surface-inset/60 data-[state=selected]:bg-re-brand-muted motion-reduce:transition-none",
            className
        )}
        {...props}
    />
))
TableRow.displayName = "TableRow"

const TableHead = React.forwardRef<
    HTMLTableCellElement,
    React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
    <th
        ref={ref}
        className={cn(
            "h-10 bg-re-surface-inset px-3 text-left align-middle font-mono text-label text-re-text-tertiary first:pl-4 last:pr-4 [&:has([role=checkbox])]:w-10",
            className
        )}
        {...props}
    />
))
TableHead.displayName = "TableHead"

const TableCell = React.forwardRef<
    HTMLTableCellElement,
    React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
    <td
        ref={ref}
        className={cn(
            "px-3 py-2.5 align-middle text-re-text-secondary first:pl-4 last:pr-4 [&:first-child]:font-medium [&:first-child]:text-re-text-primary [&:has([role=checkbox])]:pr-0",
            className
        )}
        {...props}
    />
))
TableCell.displayName = "TableCell"

const TableCaption = React.forwardRef<
    HTMLTableCaptionElement,
    React.HTMLAttributes<HTMLTableCaptionElement>
>(({ className, ...props }, ref) => (
    <caption ref={ref} className={cn("mt-4 text-small text-re-text-tertiary", className)} {...props} />
))
TableCaption.displayName = "TableCaption"

export {
    Table,
    TableHeader,
    TableBody,
    TableFooter,
    TableHead,
    TableRow,
    TableCell,
    TableCaption,
}
