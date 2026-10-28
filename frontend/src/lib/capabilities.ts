// Copy status registry. Keep these labels aligned with product availability.
export const capabilities = {
  live: ['CSV upload', 'JSON events API'],
  preview: ['EPCIS intake', 'EPCIS export'],
  planned: [],
  off: ['EDI', 'SFTP'],
} as const;

export type CapabilityStatus = keyof typeof capabilities;

export function statusOf(name: string): CapabilityStatus | undefined {
  for (const status of ['live', 'preview', 'planned', 'off'] as const) {
    if ((capabilities[status] as readonly string[]).includes(name)) return status;
  }
  return undefined;
}
