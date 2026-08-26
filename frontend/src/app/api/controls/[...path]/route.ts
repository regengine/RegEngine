import { NextResponse } from 'next/server';
import type { ProxyHandler } from '@/lib/proxy-factory';

/**
 * Compliance-overlay aliases are release-disabled with the graph subsystem.
 *
 * Keep the denial in the route handler as well as the global proxy so direct
 * handler execution, framework changes, or middleware exclusions cannot turn
 * this alias into an authenticated upstream proxy. An empty exact 404 is
 * intentionally indistinguishable from a route that does not exist.
 */
const releaseDisabled: ProxyHandler = async () => new NextResponse(null, { status: 404 });

export const dynamic = 'force-dynamic';

export const GET = releaseDisabled;
export const HEAD = releaseDisabled;
export const POST = releaseDisabled;
export const PUT = releaseDisabled;
export const PATCH = releaseDisabled;
export const DELETE = releaseDisabled;
export const OPTIONS = releaseDisabled;
