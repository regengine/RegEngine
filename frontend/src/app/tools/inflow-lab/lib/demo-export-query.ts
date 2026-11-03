/**
 * Build export query strings for the public Inflow Lab demo.
 * Empty lot / date filters are omitted so downloads default to all demo events.
 * Nonblank TLCs are passed through exactly as received (no trim/case-fold).
 */
export function buildDemoExportQuery(params: {
    preset?: string;
    traceabilityLotCode?: string;
    startDate?: string;
    endDate?: string;
}): string {
    const search = new URLSearchParams();
    const preset = params.preset?.trim();
    const lot = params.traceabilityLotCode;
    const startDate = params.startDate?.trim();
    const endDate = params.endDate?.trim();
    if (preset) search.set("preset", preset);
    if (lot != null && lot !== "") search.set("traceability_lot_code", lot);
    if (startDate) search.set("start_date", startDate);
    if (endDate) search.set("end_date", endDate);
    const query = search.toString();
    return query ? `?${query}` : "";
}
