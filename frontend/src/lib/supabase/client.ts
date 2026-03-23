import { createBrowserClient } from '@supabase/ssr'

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''

export function createSupabaseBrowserClient() {
    if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
        // Return a stub during build/prerender when env vars aren't available.
        // The real client is only needed at runtime in the browser.
        return createBrowserClient(
            'https://placeholder.supabase.co',
            'placeholder-anon-key'
        )
    }
    return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY)
}
