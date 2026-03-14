import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function updateSession(request: NextRequest) {
    let supabaseResponse = NextResponse.next({ request })

    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        {
            cookies: {
                getAll() {
                    return request.cookies.getAll()
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value }) =>
                        request.cookies.set(name, value)
                    )
                    supabaseResponse = NextResponse.next({ request })
                    cookiesToSet.forEach(({ name, value, options }) =>
                        supabaseResponse.cookies.set(name, value, options)
                    )
                },
            },
        }
    )

    const { data: { user } } = await supabase.auth.getUser()

    // Gate developer portal routes
    if (request.nextUrl.pathname.startsWith('/developer/portal')) {
        if (!user) {
            const url = request.nextUrl.clone()
            url.pathname = '/developer/login'
            url.searchParams.set('next', request.nextUrl.pathname)
            return NextResponse.redirect(url)
        }

        // Check developer profile exists and is active
        const { data: profile } = await supabase
            .from('developer_profiles')
            .select('status')
            .eq('auth_user_id', user.id)
            .single()

        if (!profile || profile.status !== 'active') {
            const url = request.nextUrl.clone()
            url.pathname = '/developer/login'
            url.searchParams.set('error', 'no_profile')
            return NextResponse.redirect(url)
        }
    }

    // Redirect logged-in developers away from login/register
    if (user && (request.nextUrl.pathname === '/developer/login' || request.nextUrl.pathname === '/developer/register')) {
        const url = request.nextUrl.clone()
        url.pathname = '/developer/portal'
        return NextResponse.redirect(url)
    }

    return supabaseResponse
}
