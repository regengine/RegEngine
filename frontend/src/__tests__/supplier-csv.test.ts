import { describe, expect, it } from 'vitest';
import { parseCSVLocally, parseCSVRecords, validateCSVLocally } from '@/lib/supplier-csv';

describe('supplier CSV local checks', () => {
  it('shares complete CSV records across preview and validation', () => {
    const csv = '\uFEFFevent_type,product_name,lot_number\r\nshipping,"Lettuce, \"\"green\"\"\r\norganic",LOT-1\r\n\r\n';
    const preview = parseCSVLocally(csv);
    const validation = validateCSVLocally(csv);
    expect(preview.totalRows).toBe(1);
    expect(preview.sampleRows[0]).toEqual(['shipping', 'Lettuce, "green"\r\norganic', 'LOT-1']);
    expect(validation.productNames).toEqual(preview.productNames);
    expect(validation.canProceed).toBe(true);
    expect(validation.eventTypeCounts).toEqual({ Shipping: 1 });
  });

  it.each(['"unclosed', 'a"b', '"a"x', 'R,lettuce'])('rejects malformed CSV %s', row => {
    expect(() => parseCSVRecords(`event_type,product_name,lot_number\n${row}`)).toThrow();
  });

  it.each(['event_type,event_type,lot_number', 'event_type,cte_type,lot_number', 'event_type,,lot_number'])('rejects ambiguous headers %s', header => {
    expect(() => parseCSVRecords(`${header}\nR,Lettuce,LOT-1`)).toThrow();
  });

  it.each(['shipping', 'S', 's', 'receiving', 'transformation', 'first_land_based_receiving', 'first_receiver', 'packing', 'distribution'])('accepts backend vocabulary %s and canonical headers', event => {
    expect(validateCSVLocally(`cte_type,product_name,tlc_code\n${event},Lettuce,LOT-1`).canProceed).toBe(true);
  });

  it('combines alias and full-name preview counts', () => {
    expect(parseCSVLocally('event_type,product_name,lot_number\ns,Lettuce,L1\nshipping,Lettuce,L2').eventTypeCounts).toEqual({ Shipping: 2 });
  });

  it.each(['made_up', '__proto__', 'constructor', 'toString'])('rejects unknown event type %s safely', event => {
    const csv = `event_type,product_name,lot_number\n${event},Lettuce,L1`;
    expect(validateCSVLocally(csv).canProceed).toBe(false);
    expect(parseCSVLocally(csv).totalRows).toBe(1);
  });

  it.each(['R,,L1', 'R,Lettuce,', ',Lettuce,L1'])('rejects empty required cells %s even beyond issue display cap', row => {
    const csv = ['event_type,product_name,lot_number', ...Array(22).fill('R,Lettuce,L1'), row].join('\n');
    expect(validateCSVLocally(csv).canProceed).toBe(false);
  });

  it('rejects files without data', () => {
    expect(validateCSVLocally('event_type,product_name,lot_number\r\n\r\n').canProceed).toBe(false);
  });
});

it.each(['D', 'd', 'depletion', 'distribution'])('previews and validates legacy shipping alias %s consistently', event => {
  const csv = `event_type,product_name,lot_number\n${event},Lettuce,L1`;
  expect(parseCSVLocally(csv).eventTypeCounts).toEqual({ Shipping: 1 });
  const validation = validateCSVLocally(csv);
  expect(validation.eventTypeCounts).toEqual({ Shipping: 1 });
  expect(validation.canProceed).toBe(true);
});
