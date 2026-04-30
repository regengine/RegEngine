import { NextRequest, NextResponse } from "next/server";
import { validateProxySession } from "@/lib/api-proxy";

export const dynamic = "force-dynamic";

const DEFAULT_LOCAL_INFLOW_LAB_URL = "http://127.0.0.1:8000";
const ALLOWED_METHODS = new Set(["GET", "POST"]);
const JSON_CONTENT_TYPES = ["application/json", "application/problem+json"];

type BoundaryMode = "simulator" | "mock-export" | "live-export";
type EndpointContract = {
    name: "health" | "status" | "records" | "lineage" | "run" | "reset" | "fixture" | "export";
    boundary: BoundaryMode;
    stream: boolean;
};

type ProxyErrorCode =
    | "INVALID_PATH"
    | "METHOD_NOT_ALLOWED"
    | "SERVICE_UNAVAILABLE"
    | "SESSION_UNAVAILABLE"
    | "UPSTREAM_AUTH_REQUIRED"
    | "UPSTREAM_FORBIDDEN"
    | "UPSTREAM_BAD_RESPONSE"
    | "UPSTREAM_ERROR";

function serviceBaseUrl() {
    return (
        process.env.INFLOW_LAB_SERVICE_URL ||
        process.env.NEXT_PUBLIC_INFLOW_LAB_SERVICE_URL ||
        DEFAULT_LOCAL_INFLOW_LAB_URL
    ).replace(/\/$/, "");
}

function proxyError(
    message: string,
    status: number,
    code: ProxyErrorCode,
    options: {
        detail?: string;
        upstreamStatus?: number;
        contract?: EndpointContract;
        hint?: string;
        correlationId?: string;
    } = {}
) {
    return NextResponse.json(
        {
            ok: false,
            error: message,
            code,
            detail: options.detail,
            upstream_status: options.upstreamStatus,
            contract: options.contract
                ? {
                    endpoint: options.contract.name,
                    boundary: options.contract.boundary,
                }
                : undefined,
            hint: options.hint,
            correlation_id: options.correlationId,
        },
        {
            status,
            headers: {
                "cache-control": "no-store",
            },
        }
    );
}

function pathFromParams(path: string[] = []) {
    if (path.some((segment) => segment === ".." || segment.includes("\0"))) {
        return null;
    }

    const joined = `/${path.map(encodeURIComponent).join("/")}`;
    return joined;
}

function endpointContract(path: string, method: string): EndpointContract | null {
    if (method === "GET" && path === "/api/healthz") {
        return { name: "health", boundary: "simulator", stream: false };
    }
    if (method === "GET" && path === "/api/simulate/status") {
        return { name: "status", boundary: "simulator", stream: false };
    }
    if (method === "GET" && path === "/api/events") {
        return { name: "records", boundary: "simulator", stream: false };
    }
    if (method === "GET" && /^\/api\/lineage\/[^/]+$/.test(path)) {
        return { name: "lineage", boundary: "simulator", stream: false };
    }
    if (method === "POST" && /^\/api\/demo-fixtures\/[^/]+\/load$/.test(path)) {
        return { name: "fixture", boundary: "simulator", stream: false };
    }
    if (method === "POST" && (path === "/api/simulate/start" || path === "/api/simulate/stop")) {
        return { name: "run", boundary: "simulator", stream: false };
    }
    if (method === "POST" && path === "/api/simulate/reset") {
        return { name: "reset", boundary: "simulator", stream: false };
    }
    if (method === "GET" && path === "/api/mock/regengine/export/fda-request") {
        return { name: "export", boundary: "mock-export", stream: true };
    }
    if (method === "GET" && path === "/api/mock/regengine/export/epcis") {
        return { name: "export", boundary: "mock-export", stream: true };
    }
    if (method === "GET" && path === "/api/regengine/export/fda-request") {
        return { name: "export", boundary: "live-export", stream: true };
    }
    if (method === "GET" && path === "/api/regengine/export/epcis") {
        return { name: "export", boundary: "live-export", stream: true };
    }

    return null;
}

function copyAllowedSearchParams(source: URLSearchParams, target: URLSearchParams) {
    for (const [key, value] of source.entries()) {
        if (/^[a-zA-Z0-9_.-]{1,64}$/.test(key)) {
            target.append(key, value);
        }
    }
}

function isJsonResponse(response: Response) {
    const contentType = response.headers.get("content-type")?.toLowerCase() || "";
    return JSON_CONTENT_TYPES.some((type) => contentType.includes(type));
}

async function readUpstreamJson(response: Response) {
    return response.json().catch(() => null) as Promise<unknown>;
}

function upstreamMessage(payload: unknown) {
    if (!payload || typeof payload !== "object") return null;
    const record = payload as Record<string, unknown>;
    for (const key of ["error", "detail", "message"]) {
        const value = record[key];
        if (typeof value === "string" && value.trim()) return value;
    }
    return null;
}

function upstreamErrorCode(status: number): ProxyErrorCode {
    if (status === 401) return "UPSTREAM_AUTH_REQUIRED";
    if (status === 403) return "UPSTREAM_FORBIDDEN";
    return "UPSTREAM_ERROR";
}

function responseHeaders(contract: EndpointContract, upstream?: Response) {
    const headers = new Headers({
        "cache-control": "no-store",
        "x-inflow-lab-contract": contract.name,
        "x-inflow-lab-boundary": contract.boundary,
    });
    const contentType = upstream?.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    const contentDisposition = upstream?.headers.get("content-disposition");
    if (contentDisposition) headers.set("content-disposition", contentDisposition);
    return headers;
}

async function proxyInflowLab(request: NextRequest, params: Promise<{ path?: string[] }>) {
    const method = request.method.toUpperCase();
    if (!ALLOWED_METHODS.has(method)) {
        return proxyError("Unsupported Inflow Lab proxy method", 405, "METHOD_NOT_ALLOWED");
    }

    const sessionError = await validateProxySession(request);
    if (sessionError) {
        const payload = await sessionError.json().catch(() => ({}));
        return proxyError(
            upstreamMessage(payload) || "Session expired or unavailable",
            401,
            "SESSION_UNAVAILABLE",
            { hint: "Refresh the page and sign in again before using live Inflow Lab actions." }
        );
    }

    const { path } = await params;
    const relativePath = pathFromParams(path);
    const contract = relativePath ? endpointContract(relativePath, method) : null;
    if (!relativePath || !contract) {
        return proxyError(
            "Invalid Inflow Lab proxy path",
            400,
            "INVALID_PATH",
            {
                hint: "Allowed Inflow Lab routes are health, status, records, lineage, run/reset, fixture load, and export links.",
            }
        );
    }

    const upstreamUrl = new URL(`${serviceBaseUrl()}${relativePath}`);
    copyAllowedSearchParams(request.nextUrl.searchParams, upstreamUrl.searchParams);

    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    const tenant = request.headers.get("x-regengine-tenant");
    if (tenant) headers.set("x-regengine-tenant", tenant);

    try {
        const upstream = await fetch(upstreamUrl, {
            method,
            headers,
            body: method === "GET" ? undefined : await request.text(),
            cache: "no-store",
        });

        if (contract.stream && upstream.ok) {
            return new NextResponse(upstream.body, {
                status: upstream.status,
                headers: responseHeaders(contract, upstream),
            });
        }

        if (!isJsonResponse(upstream)) {
            return proxyError(
                "Inflow Lab upstream returned a non-JSON response",
                upstream.ok ? 502 : upstream.status,
                "UPSTREAM_BAD_RESPONSE",
                {
                    upstreamStatus: upstream.status,
                    contract,
                    detail: upstream.headers.get("content-type") || "missing content-type",
                }
            );
        }

        const payload = await readUpstreamJson(upstream);
        if (!upstream.ok) {
            return proxyError(
                upstreamMessage(payload) || "Inflow Lab upstream request failed",
                upstream.status,
                upstreamErrorCode(upstream.status),
                { upstreamStatus: upstream.status, contract }
            );
        }

        return NextResponse.json(payload, {
            status: upstream.status,
            headers: responseHeaders(contract, upstream),
        });
    } catch (error) {
        const correlationId = crypto.randomUUID();
        console.error("[inflow-lab] Proxy request failed", { correlationId, error });
        return proxyError(
            "Inflow Lab service unavailable",
            502,
            "SERVICE_UNAVAILABLE",
            {
                hint: `Set INFLOW_LAB_SERVICE_URL or start the simulator at ${DEFAULT_LOCAL_INFLOW_LAB_URL}`,
                contract,
                correlationId,
            }
        );
    }
}

export function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
    return proxyInflowLab(request, context.params);
}

export function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
    return proxyInflowLab(request, context.params);
}
