// Copy status registry. Keep these labels aligned with product availability.
export const capabilities = {
  live: ['CSV upload', 'JSON events API'],
  preview: ['EPCIS intake', 'EPCIS export'],
  neverShown: ['EDI', 'SFTP'],
} as const;
