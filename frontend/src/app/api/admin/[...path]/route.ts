import { NextRequest, NextResponse } from 'next/server';

const DEFAULT_ADMIN_URL = 'http://localhost:8400';
const VERCEL_PRIVATE_DNS_ERROR = 'DNS_HOSTNAME_RESOLVED_PRIVATE';

// force-static for CI static export; force-dynamic on Vercel production
export const dynamic = process.env.REGENGINE_DEPLOY_MODE === 'static' ? 'force-static' : 'force-dynamic' as any;
export const generateStaticParams = process.env.REGENGINE_DEPLOY_MODE === 'static' ? async () => [{ path: ['health'] }] : undefined;

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
    const targetBases = getAdminTargets();

    const headers = new Headers();
    const hasRequestBody = !['GET', 'OPTIONS'].includes(method);
    const contentType = request.headers.get('content-type');
    if (contentType) {
      headers.set('Content-Type', contentType);
    } else if (hasRequestBody) {
      headers.set('Content-Type', 'application/json');
    }

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

    let requestBody: ArrayBuffer | undefined;
    if (hasRequestBody) {
      const bodyBuffer = await request.arrayBuffer();
      if (bodyBuffer.byteLength > 0) {
        requestBody = bodyBuffer;
        fetchOptions.body = requestBody;
      }
    }

    const attemptErrors: string[] = [];

    for (const targetBase of targetBases) {
      const targetUrl = `${stripTrailingSlash(targetBase)}/${path}${queryString}`;
      try {
        const response = await fetch(targetUrl, fetchOptions);
        if (shouldRetryResponse(response)) {
          attemptErrors.push(
            `target=${targetBase} status=${response.status} reason=${response.headers.get('x-vercel-error') || 'vercel_error'}`,
          );
          continue;
        }

        const outgoingHeaders = new Headers();
        const passthroughResponseHeaders = [
          'content-type',
          'content-disposition',
          'cache-control',
          'x-fda-record-count',
        ];
        for (const headerName of passthroughResponseHeaders) {
          const headerValue = response.headers.get(headerName);
          if (headerValue) {
            outgoingHeaders.set(headerName, headerValue);
          }
        }

        return new NextResponse(response.body, {
          status: response.status,
          headers: outgoingHeaders,
        });
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Admin request failed';
        attemptErrors.push(`target=${targetBase} error=${message}`);

        if (hasRequestBody && requestBody) {
          fetchOptions.body = requestBody;
        }
      }
    }

    return NextResponse.json(
      {
        error: 'Unable to reach admin service',
        details: attemptErrors,
      },
      { status: 502 },
    );
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Admin request failed';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

function getAdminTargets(): string[] {
  const candidates: string[] = [];
  const publicAdminUrl = process.env.NEXT_PUBLIC_ADMIN_URL;
  const publicApiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  const internalAdminUrl = process.env.ADMIN_SERVICE_URL;

  if (publicAdminUrl) {
    candidates.push(publicAdminUrl);
  }

  if (publicApiBase) {
    candidates.push(`${stripTrailingSlash(publicApiBase)}/admin`);
  }

  const runningOnVercel = Boolean(
    process.env.VERCEL || process.env.VERCEL_URL || process.env.VERCEL_ENV,
  );
  if (internalAdminUrl && (!runningOnVercel || isPublicAdminHost(internalAdminUrl))) {
    candidates.push(internalAdminUrl);
  }

  if (candidates.length === 0) {
    candidates.push(DEFAULT_ADMIN_URL);
  }

  return Array.from(new Set(candidates.map((candidate) => stripTrailingSlash(candidate))));
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function shouldRetryResponse(response: Response): boolean {
  const vercelErrorHeader = response.headers.get('x-vercel-error') || '';
  return vercelErrorHeader.includes(VERCEL_PRIVATE_DNS_ERROR);
}

function isPublicAdminHost(urlValue: string): boolean {
  try {
    const parsed = new URL(urlValue);
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return false;
    }

    const hostname = parsed.hostname.toLowerCase();
    if (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '::1' ||
      hostname.endsWith('.local') ||
      hostname.endsWith('.internal') ||
      !hostname.includes('.')
    ) {
      return false;
    }

    if (hostname.startsWith('10.')) {
      return false;
    }

    if (hostname.startsWith('192.168.')) {
      return false;
    }

    const secondOctet = Number(hostname.split('.')[1]);
    if (hostname.startsWith('172.') && secondOctet >= 16 && secondOctet <= 31) {
      return false;
    }

    return true;
  } catch {
    return false;
  }
}
