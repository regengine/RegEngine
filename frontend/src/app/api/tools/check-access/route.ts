/**
 * Lightweight check for tool access cookie.
 * Called by EmailGate on mount to decide whether to show the gate or the tool.
 *
 * GET /api/tools/check-access → { hasAccess: boolean }
 */
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
    const token = request.cookies.get('re_tool_access')?.value;
    return NextResponse.json({ hasAccess: !!token });
}
