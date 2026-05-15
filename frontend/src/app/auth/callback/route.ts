import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createServerClient } from '@supabase/ssr'
// Must be dynamic — this route exchanges OAuth codes for sessions at request time
export const dynamic = 'force-dynamic';

function resolveSafeNextPath(nextPath: string | null, origin: string): string {
    if (!nextPath) return '/dashboard'

    const trimmed = nextPath.trim()
    if (!trimmed.startsWith('/') || trimmed.startsWith('//') || /[\u0000-\u001F\u007F\\]/.test(trimmed)) {
        return '/dashboard'
    }

    try {
        const parsed = new URL(trimmed, origin)
        if (parsed.origin !== origin || parsed.pathname === '/login' || parsed.pathname.startsWith('/login/')) {
            return '/dashboard'
        }
        return `${parsed.pathname}${parsed.search}${parsed.hash}`
    } catch {
        return '/dashboard'
    }
}

function normalizePublicOrigin(value: string | null | undefined): string | null {
    if (!value) return null

    const trimmed = value.trim()
    if (!trimmed) return null

    const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
    try {
        const parsed = new URL(candidate)
        if (!['http:', 'https:'].includes(parsed.protocol)) return null
        return parsed.origin
    } catch {
        return null
    }
}

function resolveRedirectOrigin(requestOrigin: string): string {
    if (process.env.NODE_ENV === 'development') return requestOrigin

    // Fallback order:
    //   1. NEXT_PUBLIC_SITE_URL — explicit, operator-controlled override. Wins
    //      when set so an environment can pin auth redirects to a canonical
    //      alias regardless of how the request arrived.
    //   2. requestOrigin — derived from `new URL(request.url).origin`. On
    //      Vercel, `request.url`'s host is the user-facing canonical hostname
    //      that the browser actually sent the request to; it is NOT taken
    //      from `x-forwarded-host` (which is attacker-controlled). This is
    //      the same safe path the route used before PR #2358.
    //
    // VERCEL_URL is intentionally NOT consulted: it is always the
    // deployment-specific hostname (e.g. `regengine-xxxx.vercel.app`), never
    // the canonical user-facing alias. Falling back to it caused the
    // 2026-05-13 prod login outage — Supabase session cookies set on the
    // deployment origin did not stick on the alias, so every login surfaced
    // a generic "unexpected error" on the frontend.
    return (
        normalizePublicOrigin(process.env.NEXT_PUBLIC_SITE_URL) ??
        requestOrigin
    )
}

export async function GET(request: NextRequest) {
    const { searchParams, origin } = new URL(request.url)
    const code = searchParams.get('code')
    const nonce = request.headers.get('x-nonce') ?? ''
    // Default to /dashboard for regular users; developer portal flows pass ?next=/developer/portal explicitly
    const next = searchParams.get('next') ?? '/dashboard'

    if (code) {
        // Compute the redirect URL before creating the response so we can attach
        // session cookies to the redirect. Without this, exchangeCodeForSession sets
        // cookies only on request.cookies (not visible to the browser) and the session
        // is lost — causing the reset-password page to see no session.
        const redirectOrigin = resolveRedirectOrigin(origin)
        const response = NextResponse.redirect(new URL(resolveSafeNextPath(next, redirectOrigin), redirectOrigin))

        const supabase = createServerClient(
            process.env.NEXT_PUBLIC_SUPABASE_URL!,
            process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
            {
                cookies: {
                    getAll() {
                        return request.cookies.getAll()
                    },
                    // Write cookies onto the redirect response so the browser
                    // receives the Supabase session after the PKCE code exchange.
                    setAll(cookiesToSet) {
                        cookiesToSet.forEach(({ name, value, options }) =>
                            response.cookies.set(name, value, options)
                        )
                    },
                },
            }
        )

        const { error } = await supabase.auth.exchangeCodeForSession(code)
        if (!error) {
            return response
        }
    }

    // No `?code=` param — this is either an implicit-flow recovery link (old
    // emails sent before the PKCE migration) or a completely invalid/expired
    // link.  The hash fragment (#access_token=...&type=recovery) is never sent
    // to the server, so we can't read it here.  Return a minimal HTML page
    // whose inline script reads the fragment client-side and either:
    //   a) forwards an implicit recovery token to /reset-password (old emails), or
    //   b) sends the user to /forgot-password with an expiry notice.
    return new Response(
        `<!doctype html><html><head><meta charset="utf-8"></head><body><script nonce="${nonce}">
(function(){
  var h = window.location.hash;
  if (h.indexOf('type=recovery') !== -1 && h.indexOf('access_token=') !== -1) {
    window.location.replace('/reset-password' + h);
  } else {
    window.location.replace('/forgot-password?error=link_expired');
  }
})();
</script></body></html>`,
        { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
}
