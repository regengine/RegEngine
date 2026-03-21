import { NextResponse } from 'next/server';

export const runtime = 'edge';
export const dynamic = 'force-dynamic';

interface ServiceCheck {
    name: string;
    status: 'healthy' | 'unhealthy' | 'unreachable' | 'not_configured';
    code?: number;
    url?: string;
    latencyMs?: number;
}

export async function GET() {
    const services: Record<string, string | undefined> = {
        admin: process.env.ADMIN_SERVICE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_ADMIN_URL,
        compliance: process.env.COMPLIANCE_SERVICE_URL,
        ingestion: process.env.INGESTION_SERVICE_URL,
    };

    const checks: ServiceCheck[] = await Promise.all(
        Object.entries(services).map(async ([name, url]): Promise<ServiceCheck> => {
            if (!url) return { name, status: 'not_configured' };
            const start = Date.now();
            try {
                const res = await fetch(`${url}/health`, {
                    signal: AbortSignal.timeout(5000),
                    headers: { 'User-Agent': 'regengine-healthcheck/1.0' },
                });
                return {
                    name,
                    status: res.ok ? 'healthy' : 'unhealthy',
                    code: res.status,
                    latencyMs: Date.now() - start,
                };
            } catch {
                return {
                    name,
                    status: 'unreachable',
                    url: url.replace(/\/\/.*@/, '//***@'),
                    latencyMs: Date.now() - start,
                };
            }
        })
    );

    const configured = checks.filter(c => c.status !== 'not_configured');
    const healthyCount = configured.filter(c => c.status === 'healthy').length;
    const allHealthy = configured.length > 0 && healthyCount === configured.length;

    return NextResponse.json(
        {
            status: allHealthy ? 'healthy' : 'degraded',
            timestamp: new Date().toISOString(),
            services: checks,
            summary: {
                healthy: healthyCount,
                total: configured.length,
            },
        },
        { status: allHealthy ? 200 : 503 }
    );
}