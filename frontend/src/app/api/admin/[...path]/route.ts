import { NextRequest, NextResponse } from 'next/server';

const ADMIN_URL =
  process.env.ADMIN_SERVICE_URL || process.env.NEXT_PUBLIC_ADMIN_URL || 'http://localhost:8400';

export const dynamic = 'force-static';
export const generateStaticParams = async () => {
  return [{ path: ['static_proxy'] }];
};

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, 'GET');
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, 'POST');
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, 'PUT');
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, 'PATCH');
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, 'DELETE');
}

export async function OPTIONS(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, 'OPTIONS');
}

async function proxyRequest(
  request: NextRequest,
  pathParts: string[],
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS',
) {
  try {
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
      return NextResponse.json(
        { error: 'Admin API proxy unavailable during static build', static_mode: true },
        { status: 503 },
      );
    }

    const path = pathParts.join('/');
    const queryString = new URL(request.url).search;
    const targetUrl = `${ADMIN_URL}/${path}${queryString}`;

    const headers = new Headers();
    const contentType = request.headers.get('content-type');
    if (contentType) headers.set('Content-Type', contentType);

    const passthroughHeaders = [
      'authorization',
      'x-api-key',
      'x-admin-key',
      'x-regengine-api-key',
      'x-tenant-id',
    ];
    for (const key of passthroughHeaders) {
      const value = request.headers.get(key);
      if (value) {
        headers.set(key, value);
      }
    }

    const fetchOptions: RequestInit = {
      method,
      headers,
    };

    if (!['GET', 'OPTIONS'].includes(method)) {
      const bodyText = await request.text();
      if (bodyText) {
        fetchOptions.body = bodyText;
      }
    }

    const response = await fetch(targetUrl, fetchOptions);
    const responseText = await response.text();

    const outgoingHeaders = new Headers();
    const responseContentType = response.headers.get('content-type');
    if (responseContentType) outgoingHeaders.set('Content-Type', responseContentType);
    const disposition = response.headers.get('content-disposition');
    if (disposition) outgoingHeaders.set('Content-Disposition', disposition);

    return new NextResponse(responseText, {
      status: response.status,
      headers: outgoingHeaders,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Admin request failed';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
