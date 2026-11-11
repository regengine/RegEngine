/**
 * Calendar-date helpers for forms that ask "which day?".
 *
 * `new Date().toISOString().split('T')[0]` is the UTC day, not the user's:
 * from late afternoon in the Americas it is already tomorrow. A date input
 * must be pre-filled and bounded with the day on the user's own calendar.
 */

function pad(value: number): string {
    return String(value).padStart(2, '0');
}

/** Today on the user's calendar as YYYY-MM-DD, the value a date input takes. */
export function localDateInputValue(now: Date = new Date()): string {
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
