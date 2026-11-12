import type { Metadata } from 'next';
import type { ReactNode } from 'react';

const TITLE = 'Demo workspace | RegEngine';
const DESCRIPTION =
  'A public, read-only RegEngine workspace. Five supply chains of synthetic data modelled on FDA major recall notices: import, fix queue, evidence ledger and export packages. No account needed.';

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/demo' },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: 'https://regengine.co/demo',
    type: 'website',
    images: [{ url: '/og-image.png', width: 1200, height: 630, alt: 'RegEngine demo workspace' }],
  },
};

export default function DemoLayout({ children }: { children: ReactNode }) {
  return children;
}
