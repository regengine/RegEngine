import { createBrowserClient } from '@supabase/ssr'

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
let hasWarnedMissingSupabaseConfig = false

export function isSupabaseConfigured() {
    return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY)
}

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

export function createSupabaseBrowserClient() {
    if (!isSupabaseConfigured()) {
        warnMissingSupabaseConfig()
        // Return a stub during build/prerender when env vars aren't available.
        // The real client is only needed at runtime in the browser.
        return createBrowserClient(
            'https://placeholder.supabase.co',
            'placeholder-anon-key'
        )
    }
    return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY)
}
