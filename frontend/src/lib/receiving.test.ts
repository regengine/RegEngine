import fixture from '../__tests__/fixtures/receiving-event.json';
import { describe, expect, it } from 'vitest';
import { buildReceivingEvent, interpretReceivingResults, receivingSubmission } from './receiving';
const item = { id: 'row-1', lotCode: 'observed-lot', gtin: '00614141000012', productName: 'Lettuce', quantity: 2, scannedAt: '2026-10-01T12:00:00Z' };
const context = { supplier: 'Farm A', poNumber: 'PO-1', receivingLocation: 'Dock A', tlcSourceReference: 'Farm A address' };
describe('receiving contract', () => {
 it('provides every receiving KDE without substituting a barcode for a lot', () => {
  expect(JSON.parse(JSON.stringify(buildReceivingEvent(item, context)))).toEqual(fixture);
  expect(buildReceivingEvent(item, context).kdes).toMatchObject({ receive_date: '2026-10-01', receiving_location: 'Dock A', immediate_previous_source: 'Farm A', reference_document: 'PO-1', tlc_source_reference: 'Farm A address' });
  expect(() => buildReceivingEvent({ ...item, lotCode: '' }, context)).toThrow(/lot/i);
 });
 it('keeps an unchanged retry identity and rotates it for changed payload', () => {
  const first = receivingSubmission('tenant', [item], context);
  expect(receivingSubmission('tenant', [item], context, first)).toEqual(first);
  expect(receivingSubmission('tenant', [{ ...item, quantity: 3 }], context, first).key).not.toEqual(first.key);
 });
 it('blocks duplicate lot identities before sending an ambiguous batch', () => {
  expect(() => receivingSubmission('tenant', [item, { ...item, id: 'row-2' }], context)).toThrow(/unique/i);
 });
 it('requires durable accepted events and retains mixed rejected rows', () => {
  const rows = [item, { ...item, id: 'row-2', lotCode: 'lot-2' }];
  expect(interpretReceivingResults(rows, { accepted: 1, rejected: 1, total: 2, events: [{ traceability_lot_code: 'lot-2', status: 'rejected', errors: ['Missing source'] }, { traceability_lot_code: 'observed-lot', status: 'accepted', event_id: 'event-1' }] })).toEqual({ acceptedIds: ['row-1'], errors: { 'row-2': 'Missing source' } });
  expect(interpretReceivingResults([item], { accepted: 1, rejected: 0, total: 1, events: [{ traceability_lot_code: 'observed-lot', status: 'accepted' }] }).acceptedIds).toEqual([]);
 });
});
