import { NextRequest, NextResponse } from "next/server";
import {
    CSRF_HEADER,
    CSRF_PROTECTED_METHODS,
    CSRF_SIG_COOKIE,
    verifyCsrfToken,
} from "@/lib/csrf";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DEFAULT_LOCAL_INFLOW_LAB_URL = "http://127.0.0.1:8000";
const ALLOWED_METHODS = new Set(["GET", "POST"]);
const JSON_CONTENT_TYPES = ["application/json", "application/problem+json"];
const MAX_BODY_BYTES = 32 * 1024;
const TENANT_LIKE_KEY = /^(tenant(_?id)?|tenantId|customer(_?id)?|customerId|organization(_?id)?|org_id|orgId)$/i;

// Best-effort per-instance token bucket (same posture as /api/client-errors).
const DEFAULT_WINDOW_MS = 60_000;
const DEFAULT_MAX_PER_WINDOW = 60;
const MAX_TRACKED_IPS = 10_000;
const buckets = new Map<string, { count: number; windowStart: number }>();

type DemoContract =
    | "health"
    | "status"
    | "events"
    | "lineage"
    | "start"
    | "stop"
    | "reset"
    | "fixture";

function serviceBaseUrl() {
    return (
        process.env.INFLOW_LAB_SERVICE_URL ||
        DEFAULT_LOCAL_INFLOW_LAB_URL
    ).replace(/\/$/, "");
}

function demoProxyEnabled() {
    if (process.env.NODE_ENV !== "production") return true;
    const value = process.env.REGENGINE_ENABLE_INFLOW_LAB_DEMO_PROXY?.trim().toLowerCase();
    return value === "1" || value === "true";
}

function basicAuthHeader() {
    const username = process.env.INFLOW_LAB_BASIC_AUTH_USERNAME;
    const password = process.env.INFLOW_LAB_BASIC_AUTH_PASSWORD;
    if (!username || !password) return null;
    return `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
}

function rateWindowMs() {
    const raw = Number(process.env.INFLOW_LAB_DEMO_RATE_WINDOW_MS || "");
    return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_WINDOW_MS;
}

function rateMaxPerWindow() {
    const raw = Number(process.env.INFLOW_LAB_DEMO_RATE_MAX || "");
    return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_MAX_PER_WINDOW;
}

/** Test-only: clear in-memory buckets between cases. */
export function __resetInflowLabDemoRateLimitForTests() {
    buckets.clear();
}

function clientIp(request: NextRequest): string {
    const xff = request.headers.get("x-forwarded-for");
    if (xff) return xff.split(",")[0]?.trim() || "unknown";
    return request.headers.get("x-real-ip") || "unknown";
}

function allowIp(ip: string): boolean {
    const now = Date.now();
    const windowMs = rateWindowMs();
    const max = rateMaxPerWindow();
    const bucket = buckets.get(ip);
    if (!bucket || now - bucket.windowStart >= windowMs) {
        if (buckets.size >= MAX_TRACKED_IPS) {
            for (const [key, value] of buckets) {
                if (now - value.windowStart >= windowMs) buckets.delete(key);
            }
            if (buckets.size >= MAX_TRACKED_IPS) buckets.clear();
        }
        buckets.set(ip, { count: 1, windowStart: now });
        return true;
    }
    bucket.count += 1;
    return bucket.count <= max;
}

function pathFromParams(path: string[] = []) {
    if (path.some((segment) => segment === ".." || segment.includes("\0"))) {
        return null;
    }
    return `/${path.map(encodeURIComponent).join("/")}`;
}

function demoContract(path: string, method: string): DemoContract | null {
    if (method === "GET" && path === "/api/healthz") return "health";
    if (method === "GET" && path === "/api/simulate/status") return "status";
    if (method === "GET" && path === "/api/events") return "events";
    if (method === "GET" && /^\/api\/lineage\/[^/]+$/.test(path)) return "lineage";
    if (method === "POST" && path === "/api/simulate/start") return "start";
    if (method === "POST" && path === "/api/simulate/stop") return "stop";
    if (method === "POST" && path === "/api/simulate/reset") return "reset";
    if (method === "POST" && /^\/api\/demo-fixtures\/[^/]+\/load$/.test(path)) return "fixture";
    return null;
}

function copyAllowedSearchParams(source: URLSearchParams, target: URLSearchParams) {
    for (const [key, value] of source.entries()) {
        if (TENANT_LIKE_KEY.test(key)) continue;
        if (/^[a-zA-Z0-9_.-]{1,64}$/.test(key)) {
            target.append(key, value.slice(0, 256));
        }
    }
}

function isJsonResponse(response: Response) {
    const contentType = response.headers.get("content-type")?.toLowerCase() || "";
    return JSON_CONTENT_TYPES.some((type) => contentType.includes(type));
}

function stripTenantLike(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(stripTenantLike);
    if (value && typeof value === "object") {
        const out: Record<string, unknown> = {};
        for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
            if (TENANT_LIKE_KEY.test(key)) continue;
            out[key] = stripTenantLike(child);
        }
        return out;
    }
    return value;
}

function sameOriginAllowed(request: NextRequest, requirePresent: boolean): boolean {
    const sourceUrl = request.headers.get("origin") || request.headers.get("referer");
    if (!sourceUrl) return !requirePresent;
    try {
        return new URL(sourceUrl).origin === request.nextUrl.origin;
    } catch {
        return false;
    }
}

async function enforceCsrf(request: NextRequest): Promise<NextResponse | null> {
    const method = request.method.toUpperCase();
    if (!CSRF_PROTECTED_METHODS.has(method)) return null;

    if (!sameOriginAllowed(request, true)) {
        return NextResponse.json(
            { ok: false, error: "Cross-origin mutation rejected", code: "CROSS_ORIGIN" },
            { status: 403, headers: { "cache-control": "no-store" } },
        );
    }

    const headerToken = request.headers.get(CSRF_HEADER);
    const sigCookie = request.cookies.get(CSRF_SIG_COOKIE)?.value;
    if (!headerToken || !sigCookie) {
        return NextResponse.json(
            { ok: false, error: "Missing CSRF token", code: "CSRF_MISSING" },
            { status: 403, headers: { "cache-control": "no-store" } },
        );
    }
    const valid = await verifyCsrfToken(headerToken, sigCookie);
    if (!valid) {
        return NextResponse.json(
            { ok: false, error: "Invalid CSRF token", code: "CSRF_INVALID" },
            { status: 403, headers: { "cache-control": "no-store" } },
        );
    }
    return null;
}

async function readSanitizedBody(request: NextRequest): Promise<
    { ok: true; body?: string } | { ok: false; response: NextResponse }
> {
    if (request.method.toUpperCase() === "GET") return { ok: true };

    const raw = await request.text();
    if (raw.length > MAX_BODY_BYTES) {
        return {
            ok: false,
            response: NextResponse.json(
                { ok: false, error: "Request body too large", code: "BODY_TOO_LARGE" },
                { status: 413, headers: { "cache-control": "no-store" } },
            ),
        };
    }
    if (!raw.trim()) return { ok: true, body: undefined };

    const contentType = request.headers.get("content-type")?.toLowerCase() || "";
    if (!contentType.includes("application/json")) {
        return {
            ok: false,
            response: NextResponse.json(
                { ok: false, error: "JSON body required", code: "INVALID_CONTENT_TYPE" },
                { status: 415, headers: { "cache-control": "no-store" } },
            ),
        };
    }

    let parsed: unknown;
    try {
        parsed = JSON.parse(raw) as unknown;
    } catch {
        return {
            ok: false,
            response: NextResponse.json(
                { ok: false, error: "Invalid JSON body", code: "INVALID_JSON" },
                { status: 400, headers: { "cache-control": "no-store" } },
            ),
        };
    }

    return { ok: true, body: JSON.stringify(stripTenantLike(parsed)) };
}

function responseHeaders(contract: DemoContract, upstream?: Response) {
    const headers = new Headers({
        "cache-control": "no-store",
        "x-inflow-lab-demo-contract": contract,
        "x-inflow-lab-boundary": "public-demo",
    });
    const contentType = upstream?.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    return headers;
}

async function proxyDemo(request: NextRequest, params: Promise<{ path?: string[] }>) {
    if (!demoProxyEnabled()) {
        return new NextResponse(null, { status: 404 });
    }

    const method = request.method.toUpperCase();
    if (!ALLOWED_METHODS.has(method)) {
        return NextResponse.json(
            { ok: false, error: "Method not allowed", code: "METHOD_NOT_ALLOWED" },
            { status: 405, headers: { "cache-control": "no-store" } },
        );
    }

    // Cross-origin GETs with an explicit foreign Origin/Referer are rejected
    // even though CSRF only applies to mutations.
    if (!sameOriginAllowed(request, false)) {
        return NextResponse.json(
            { ok: false, error: "Cross-origin request rejected", code: "CROSS_ORIGIN" },
            { status: 403, headers: { "cache-control": "no-store" } },
        );
    }

    const csrfError = await enforceCsrf(request);
    if (csrfError) return csrfError;

    if (!allowIp(clientIp(request))) {
        return NextResponse.json(
            { ok: false, error: "Rate limit exceeded", code: "RATE_LIMITED" },
            {
                status: 429,
                headers: {
                    "cache-control": "no-store",
                    "Retry-After": String(Math.ceil(rateWindowMs() / 1000)),
                },
            },
        );
    }

    const { path } = await params;
    const relativePath = pathFromParams(path);
    const contract = relativePath ? demoContract(relativePath, method) : null;
    if (!relativePath || !contract) {
        return NextResponse.json(
            {
                ok: false,
                error: "Not found",
                code: "NOT_ALLOWLISTED",
                hint: "Public demo proxy allows healthz, simulate status/start/stop/reset, events, lineage, and demo-fixtures load only.",
            },
            { status: 404, headers: { "cache-control": "no-store" } },
        );
    }

    const bodyResult = await readSanitizedBody(request);
    if (!bodyResult.ok) return bodyResult.response;

    const upstreamUrl = new URL(`${serviceBaseUrl()}${relativePath}`);
    copyAllowedSearchParams(request.nextUrl.searchParams, upstreamUrl.searchParams);

    // Fresh minimal headers only — never forward browser cookies, Authorization,
    // or caller tokens. Server-held Basic auth is attached when configured.
    const headers = new Headers();
    if (bodyResult.body !== undefined) {
        headers.set("content-type", "application/json");
    }
    const authorization = basicAuthHeader();
    if (authorization) headers.set("authorization", authorization);

    try {
        const upstream = await fetch(upstreamUrl, {
            method,
            headers,
            body: method === "GET" ? undefined : bodyResult.body,
            cache: "no-store",
            redirect: "manual",
            // Explicitly omit credentials so no ambient cookie jar can attach.
            credentials: "omit",
        });

        if (upstream.status >= 300 && upstream.status < 400) {
            return NextResponse.json(
                { ok: false, error: "Upstream redirect refused", code: "UPSTREAM_BAD_RESPONSE" },
                { status: 502, headers: responseHeaders(contract) },
            );
        }

        if (!isJsonResponse(upstream)) {
            return NextResponse.json(
                {
                    ok: false,
                    error: "Upstream returned a non-JSON response",
                    code: "UPSTREAM_BAD_RESPONSE",
                    detail: upstream.headers.get("content-type") || "missing content-type",
                },
                {
                    status: upstream.ok ? 502 : upstream.status,
                    headers: responseHeaders(contract),
                },
            );
        }

        const payload = await upstream.json().catch(() => null);
        return NextResponse.json(payload, {
            status: upstream.status,
            headers: responseHeaders(contract, upstream),
        });
    } catch (error) {
        const correlationId = crypto.randomUUID();
        console.error("[inflow-lab-demo] Proxy request failed", { correlationId, error });
        return NextResponse.json(
            {
                ok: false,
                error: "Inflow Lab demo service unavailable",
                code: "SERVICE_UNAVAILABLE",
                correlation_id: correlationId,
            },
            { status: 502, headers: responseHeaders(contract) },
        );
    }
}

export function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
    return proxyDemo(request, context.params);
}

export function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
    return proxyDemo(request, context.params);
}
