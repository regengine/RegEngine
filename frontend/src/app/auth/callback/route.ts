import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createServerClient } from '@supabase/ssr'
// Must be dynamic — this route exchanges OAuth codes for sessions at request time
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
    const { searchParams, origin } = new URL(request.url)
    const code = searchParams.get('code')
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

    return NextResponse.redirect(`${origin}/login?error=auth_failed`)
}
