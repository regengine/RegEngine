/** RFC 4180 field escaping for small demo CSV serializers. Quote a field when it
 * carries a comma, quote, or line break, doubling embedded quotes so a
 * quote-aware parser recovers the original value and field count. */

export function escapeCsvField(value: string): string {
  if (value.includes('"') || value.includes(',') || value.includes('\n') || value.includes('\r')) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function toCsvLine(values: string[]): string {
  return values.map(escapeCsvField).join(',');
}
