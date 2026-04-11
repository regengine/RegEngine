import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const alt = 'RegEngine — FSMA 204 Food Traceability Compliance'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: 'linear-gradient(135deg, #06090f 0%, #0c1017 50%, #111827 100%)',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
          <div style={{ width: '64px', height: '64px', borderRadius: '16px', background: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
          </div>
          <span style={{ fontSize: '56px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-1px' }}>
            RegEngine
          </span>
        </div>
        <div style={{ fontSize: '28px', color: '#10b981', fontWeight: 600, marginBottom: '12px' }}>
          FSMA 204 Food Traceability Compliance
        </div>
        <div style={{ fontSize: '20px', color: '#94a3b8', maxWidth: '700px', textAlign: 'center', lineHeight: 1.5 }}>
          Ingest supplier data. Verify chain of custody. Export audit-ready records in minutes.
        </div>
      </div>
    ),
    { ...size }
  )
}
