/**
 * Shared empty-value placeholders. Use these instead of a bare dash so empty
 * UI states read as intentional copy:
 *
 * - NOT_SET: a field the user or upstream system has not provided (settings,
 *   profile fields, optional record attributes).
 * - NO_DATA_YET: a metric or count with no underlying data yet.
 *
 * Real zeros stay 0. Never use these where logic compares against the
 * placeholder (for example the recall-report grade sentinels).
 */
export const NOT_SET = 'Not set';
export const NO_DATA_YET = 'No data yet';
