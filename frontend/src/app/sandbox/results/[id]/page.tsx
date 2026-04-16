import { notFound } from 'next/navigation';
import { SharedSandboxResult } from './SharedSandboxResult';

interface Props {
  params: Promise<{ id: string }>;
}

async function fetchSharedResult(id: string) {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || process.env.VERCEL_URL
    ? `https://${process.env.VERCEL_URL}`
    : 'http://localhost:3000';

  const res = await fetch(`${baseUrl}/api/ingestion/api/v1/sandbox/share/${id}`, {
    cache: 'no-store',
  });

  if (res.status === 404) return null;
  if (!res.ok) return null;
  return res.json();
}

export default async function SharedResultPage({ params }: Props) {
  const { id } = await params;

  if (!id || id.length > 20) notFound();

  const result = await fetchSharedResult(id);
  if (!result) notFound();

  return <SharedSandboxResult result={result} shareId={id} />;
}

export async function generateMetadata({ params }: Props) {
  const { id } = await params;
  return {
    title: `FSMA 204 Compliance Report | RegEngine`,
    description: `Shared sandbox compliance evaluation result (${id})`,
  };
}
