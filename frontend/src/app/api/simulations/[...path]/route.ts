import { NextRequest, NextResponse } from "next/server";

const INGESTION_URL = process.env.INGESTION_SERVICE_URL || "http://localhost:8002";

export const dynamic = "force-static";
export const generateStaticParams = async () => {
  return [{ path: ["static_proxy"] }];
};

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, "GET");
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyRequest(request, path, "POST");
}

async function proxyRequest(
  request: NextRequest,
  pathParts: string[],
  method: "GET" | "POST",
) {
  try {
    if (process.env.REGENGINE_DEPLOY_MODE === "static") {
      return NextResponse.json(
        {
          error: "Simulation API proxy unavailable during static build",
          static_mode: true,
        },
        { status: 503 },
      );
    }

    const path = pathParts.join("/");
    const url = new URL(request.url);
    const queryString = url.search;
    const targetUrl = `${INGESTION_URL}/api/v1/simulations/${path}${queryString}`;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    const configuredApiKey = process.env.INGESTION_API_KEY;
    if (configuredApiKey) {
      headers["X-RegEngine-API-Key"] = configuredApiKey;
    }

    const fetchOptions: RequestInit = {
      method,
      headers,
    };

    if (method === "POST") {
      try {
        const body = await request.json();
        fetchOptions.body = JSON.stringify(body);
      } catch {
        fetchOptions.body = JSON.stringify({});
      }
    }

    const response = await fetch(targetUrl, fetchOptions);
    const text = await response.text();

    let payload: unknown = text;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = text;
    }

    const outgoingHeaders = new Headers();
    const disposition = response.headers.get("Content-Disposition");
    if (disposition) {
      outgoingHeaders.set("Content-Disposition", disposition);
    }

    if (!response.ok) {
      return NextResponse.json(
        typeof payload === "object" && payload !== null
          ? payload
          : { error: "Simulation request failed" },
        { status: response.status, headers: outgoingHeaders },
      );
    }

    if (typeof payload === "object" && payload !== null) {
      return NextResponse.json(payload, { status: response.status, headers: outgoingHeaders });
    }

    return new NextResponse(typeof payload === "string" ? payload : "", {
      status: response.status,
      headers: outgoingHeaders,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Simulation proxy request failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
