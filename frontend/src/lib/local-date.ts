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

/** Today on the UTC calendar as YYYY-MM-DD. */
export function utcDateInputValue(now: Date = new Date()): string {
    return `${now.getUTCFullYear()}-${pad(now.getUTCMonth() + 1)}-${pad(now.getUTCDate())}`;
}

/**
 * The latest ship date a supplier can submit right now.
 *
 * Shipping records are dated in UTC and the server refuses a date that has
 * not started in UTC yet. So the limit is the earlier of the supplier's own
 * today and UTC's today: behind UTC that is their local day; ahead of UTC,
 * early in their day, it is still the UTC day (their yesterday).
 */
export function latestShipDateInputValue(now: Date = new Date()): string {
    const local = localDateInputValue(now);
    const utc = utcDateInputValue(now);
    return local < utc ? local : utc;
}

/** True when the supplier's local day has started but the UTC day has not. */
export function localDayIsAheadOfUtc(now: Date = new Date()): boolean {
    return localDateInputValue(now) > utcDateInputValue(now);
}

/**
 * What the ship-date input starts as.
 *
 * Normally today. When the supplier's day is ahead of UTC, today cannot be
 * submitted yet, and pre-filling the latest allowed date would be their
 * yesterday: a supplier who ships today and does not look at the field would
 * record the wrong ship date. So the field starts empty and they must choose.
 */
export function defaultShipDateInputValue(now: Date = new Date()): string {
    return localDayIsAheadOfUtc(now) ? '' : latestShipDateInputValue(now);
}
