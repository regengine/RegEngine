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
