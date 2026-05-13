import { getSupabaseConfig, isSupabaseConfigured } from './config'

export { isSupabaseConfigured } from './config'

let hasWarnedMissingSupabaseConfig = false

function warnMissingSupabaseConfig() {
    if (process.env.NODE_ENV === 'production' || hasWarnedMissingSupabaseConfig) {
        return
    }

    hasWarnedMissingSupabaseConfig = true
    console.warn(
        '[Supabase] NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY is not set. ' +
        'Browser auth features that depend on Supabase will be skipped.'
    )
}

export async function createSupabaseBrowserClient() {
    const { createBrowserClient } = await import('@supabase/ssr')
    const { url, anonKey } = getSupabaseConfig()
    if (!isSupabaseConfigured()) {
        warnMissingSupabaseConfig()
        // Return a stub during build/prerender when env vars aren't available.
        // The real client is only needed at runtime in the browser.
        return createBrowserClient(
            'https://placeholder.supabase.co',
            'placeholder-anon-key'
        )
    }
    return createBrowserClient(url, anonKey)
}
