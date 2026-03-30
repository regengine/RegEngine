/** Shared types for the Compliance Sandbox grid editor. */

export interface CellError {
  ruleTitle: string;
  severity: string;
  whyFailed: string;
  citation: string | null;
  remediation: string | null;
  category: string;
  /** Whether this is a KDE (missing field) error vs a rule failure */
  isKdeError: boolean;
  /** Structured evidence from the rules engine (mass balance totals, temporal violations, etc.) */
  evidence?: Record<string, unknown>[];
}

/** A guided resolution option generated from error evidence. */
export interface ResolutionOption {
  id: string;
  label: string;
  description: string;
  action: 'add_row' | 'edit_cell' | 'mass_fill';
  /** For add_row: CTE type and pre-filled field values */
  cteType?: string;
  prefill?: Record<string, string>;
  /** For edit_cell: which cell to focus */
  targetColumn?: string;
  targetRow?: number;
  /** For mass_fill: column and value to fill */
  fillColumn?: string;
  fillValue?: string;
}

/** Key format: "rowIndex:columnName" */
export type CellErrorMap = Map<string, CellError[]>;

/** Key format: "rowIndex:columnName" */
export type CellFixedSet = Set<string>;

export interface GridRow {
  [column: string]: string;
}

export function cellKey(row: number, col: string): string {
  return `${row}:${col}`;
}
