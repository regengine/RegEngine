import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createServerClient } from '@supabase/ssr'
// Must be dynamic — this route exchanges OAuth codes for sessions at request time
export const dynamic = 'force-dynamic';

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
        const forwardedHost = request.headers.get('x-forwarded-host')
        const isLocalEnv = process.env.NODE_ENV === 'development'
        const redirectBase = isLocalEnv
            ? origin
            : forwardedHost
            ? `https://${forwardedHost}`
            : origin

        const response = NextResponse.redirect(`${redirectBase}${next}`)

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
