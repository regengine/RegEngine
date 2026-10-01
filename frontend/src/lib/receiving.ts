/** Receiving wire contract; expected identities must never substitute for observations. */
export interface ReceivingItem {
    id: string; gtin: string; lotCode: string; productName: string; quantity: number;
    scannedAt?: string; expiryDate?: string;
}
export interface ReceivingContext {
    supplier: string; poNumber: string; receivingLocation: string; tlcSourceReference: string;
}
export function buildReceivingEvent(item: ReceivingItem, context: ReceivingContext) {
    if (!item.lotCode.trim()) throw new Error('Enter the observed lot code for every scanned item.');
    if (!item.productName.trim() || !Number.isFinite(item.quantity) || item.quantity <= 0) throw new Error('Enter a product description and positive quantity.');
    if (Object.values(context).some(value => !value.trim())) throw new Error('Enter supplier, PO / ASN, receiving location and TLC source reference.');
    if (!item.scannedAt) throw new Error('Scan the item before submitting.');
    return {
        cte_type: 'receiving', traceability_lot_code: item.lotCode,
        product_description: item.productName, quantity: item.quantity, unit_of_measure: 'cases',
        timestamp: item.scannedAt, location_name: context.receivingLocation,
        kdes: { gtin: item.gtin || undefined, lot_code: item.lotCode, expiry_date: item.expiryDate || undefined,
            receive_date: item.scannedAt.slice(0, 10), receiving_location: context.receivingLocation,
            immediate_previous_source: context.supplier, ship_from_location: context.supplier,
            reference_document: context.poNumber, tlc_source_reference: context.tlcSourceReference,
            po_number: context.poNumber, supplier_name: context.supplier },
    };
}
export interface ReceivingSubmission { body: string; key: string }
export function receivingSubmission(tenant: string, items: ReceivingItem[], context: ReceivingContext, previous?: ReceivingSubmission): ReceivingSubmission {
    if (new Set(items.map(item => item.lotCode)).size !== items.length) throw new Error('Each submitted lot must be unique. Review duplicate observations before ingesting.');
    const body = JSON.stringify({ source: 'receiving_dock', tenant_id: tenant, events: items.map(item => buildReceivingEvent(item, context)) });
    return previous?.body === body ? previous : { body, key: crypto.randomUUID() };
}
interface EventResult { traceability_lot_code?: string; cte_type?: string; status?: string; event_id?: string; errors?: string[] }
export function interpretReceivingResults(items: ReceivingItem[], payload: unknown): { acceptedIds: string[]; errors: Record<string, string> } {
    const data = payload as { accepted?: number; rejected?: number; total?: number; events?: EventResult[] } | null;
    const events = Array.isArray(data?.events) ? data.events.filter(event => event && typeof event === 'object') : [];
    const acceptedIds: string[] = [];
    const errors: Record<string, string> = {};
    const completeEnvelope = data?.total === items.length && events.length === items.length && data.accepted! + data.rejected! === items.length && events.filter(event => event.status === 'accepted').length === data.accepted && events.filter(event => event.status === 'rejected').length === data.rejected;
    for (const item of items) {
        const results = events.filter(event => event.traceability_lot_code === item.lotCode);
        // Duplicate lot identities are deliberately unconfirmed rather than assigning a receipt to the wrong row.
        const uniqueRow = items.filter(row => row.lotCode === item.lotCode).length === 1;
        const result = results.length === 1 && uniqueRow ? results[0] : undefined;
        if (completeEnvelope && result?.status === 'accepted' && typeof result.event_id === 'string' && result.event_id.trim() && !result.errors?.length && (!result.cte_type || result.cte_type === 'receiving')) acceptedIds.push(item.id);
        else errors[item.id] = result?.errors?.join('; ') || 'Persistence was not confirmed. Review this item and retry.';
    }
    return { acceptedIds, errors };
}
