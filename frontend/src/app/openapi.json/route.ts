import { NextResponse } from 'next/server';

import { publicOpenApiSpec } from '@/lib/public-openapi';

export const dynamic = 'force-static';

export async function GET() {
  return NextResponse.json(publicOpenApiSpec, {
    headers: {
      'Cache-Control': 'public, max-age=300, s-maxage=3600',
    },
  });
}
