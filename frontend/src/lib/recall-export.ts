/** Same inclusive date range contract as the synchronous FDA export API. */
export function exportWindowParams(start: string, end: string): URLSearchParams {
  if (!start || !end) throw new Error('Start and end dates are required.');
  const parse = (value: string) => {
    const date = new Date(`${value}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
      throw new Error('Enter valid export dates.');
    }
    return date.getTime();
  };
  const days = (parse(end) - parse(start)) / 86400000;
  if (days < 0) throw new Error('End date must be on or after start date.');
  if (days > 90) throw new Error('Choose an export window of 90 days or fewer.');
  return new URLSearchParams({ start_date: start, end_date: end, format: 'csv' });
}
