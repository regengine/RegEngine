import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const DEFAULT_LOCAL_INFLOW_LAB_URL = "http://127.0.0.1:8000";
const ALLOWED_METHODS = new Set(["GET", "POST"]);

function serviceBaseUrl() {
    return (
        process.env.INFLOW_LAB_SERVICE_URL ||
        process.env.NEXT_PUBLIC_INFLOW_LAB_SERVICE_URL ||
        DEFAULT_LOCAL_INFLOW_LAB_URL
    ).replace(/\/$/, "");
}

function pathFromParams(path: string[] = []) {
    if (path.some((segment) => segment === ".." || segment.includes("\0"))) {
        return null;
    }

    const joined = `/${path.map(encodeURIComponent).join("/")}`;
    if (!joined.startsWith("/api/") && joined !== "/docs" && joined !== "/openapi.json") {
        return null;
    }

    return joined;
}

async function proxyInflowLab(request: NextRequest, params: Promise<{ path?: string[] }>) {
    const method = request.method.toUpperCase();
    if (!ALLOWED_METHODS.has(method)) {
        return NextResponse.json({ error: "Unsupported Inflow Lab proxy method" }, { status: 405 });
    }

    const { path } = await params;
    const relativePath = pathFromParams(path);
    if (!relativePath) {
        return NextResponse.json({ error: "Invalid Inflow Lab proxy path" }, { status: 400 });
    }

    const upstreamUrl = new URL(`${serviceBaseUrl()}${relativePath}`);
    request.nextUrl.searchParams.forEach((value, key) => {
        upstreamUrl.searchParams.set(key, value);
    });

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

        return new NextResponse(upstream.body, {
            status: upstream.status,
            headers: {
                "content-type": upstream.headers.get("content-type") || "application/octet-stream",
                "cache-control": "no-store",
            },
        });
    } catch {
        return NextResponse.json(
            {
                error: "Inflow Lab service unavailable",
                hint: `Set INFLOW_LAB_SERVICE_URL or start the simulator at ${DEFAULT_LOCAL_INFLOW_LAB_URL}`,
            },
            { status: 502 }
        );
    }
}

export function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
    return proxyInflowLab(request, context.params);
}

export function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
    return proxyInflowLab(request, context.params);
}
