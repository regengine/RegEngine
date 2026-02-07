import { Providers } from '@/lib/providers'
import './globals.css'
import { MarketingHeader } from '@/components/layout/marketing-header'
import { MarketingFooter } from '@/components/layout/marketing-footer'
import { Analytics } from '@vercel/analytics/react'

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        className="min-h-screen flex flex-col"
        style={{ background: "#06090f", color: "#c8d1dc" }}
        suppressHydrationWarning
      >
        <Providers>
          <MarketingHeader />
          <main className="flex-grow">
            {children}
          </main>
          <MarketingFooter />
        </Providers>
        <Analytics />
      </body>
    </html>
  )
}

