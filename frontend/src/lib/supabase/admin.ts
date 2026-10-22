import 'server-only';

import { createClient } from '@supabase/supabase-js';

// Server-only Supabase client authenticated with the secret (service-role) key.
// The 'server-only' import makes the build fail if a client component pulls
// this module in, so the key can never ship in a browser bundle. Never read
// the key from a NEXT_PUBLIC_ variable: those are inlined into client code.
export function createSupabaseAdminClient() {
  // Empty or whitespace-only values count as unset so the fallback still applies.
  const url = process.env.SUPABASE_URL?.trim() || process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.SUPABASE_SECRET_KEY?.trim() || process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();

  if (!url || !key) {
    throw new Error('Supabase admin client is not configured.');
  }

  return createClient(url, key, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  });
}
