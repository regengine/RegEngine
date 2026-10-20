import { describe, expect, it } from 'vitest';
import { escapeCsvField, toCsvLine } from '@/lib/csv-serialize';
import { parseCSVRecords } from '@/lib/supplier-csv';

/** Demo export locations carry commas, so the manifest CSV must quote them. */
describe('demo export CSV quoting', () => {
  it('quotes a location that carries a comma', () => {
    expect(escapeCsvField('Farm A, California')).toBe('"Farm A, California"');
  });

  it('leaves plain fields alone and doubles embedded quotes', () => {
    expect(escapeCsvField('Romaine Lettuce')).toBe('Romaine Lettuce');
    expect(escapeCsvField('Say "hi"')).toBe('"Say ""hi"""');
  });

  it('keeps nine fields under a nine-column header through a quote-aware parse', () => {
    const header = ['tlc', 'product', 'quantity', 'uom', 'event_date', 'event_type', 'location', 'sha256_hash', 'chain_hash'];
    const row = ['TLC-2024-001', 'Romaine Lettuce', '50', 'lbs', '2024-01-15', 'harvesting', 'Farm A, California', 'abc123', 'def456'];
    const line = toCsvLine(row);
    // The old naive join produced ten fields here; quoting keeps the location whole.
    expect(line.split(',').length).toBe(10);
    const parsed = parseCSVRecords(`${header.join(',')}\n${line}`);
    expect(parsed).toHaveLength(2);
    expect(parsed[1]).toHaveLength(9);
    expect(parsed[1][6]).toBe('Farm A, California');
  });
});
