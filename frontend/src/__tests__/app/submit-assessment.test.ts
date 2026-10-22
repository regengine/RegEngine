import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { rpc, createClient } = vi.hoisted(() => {
  const rpc = vi.fn();
  return { rpc, createClient: vi.fn(() => ({ rpc })) };
});
vi.mock('@supabase/supabase-js', () => ({ createClient }));

const ENV_KEYS = [
  'SUPABASE_URL',
  'NEXT_PUBLIC_SUPABASE_URL',
  'SUPABASE_SECRET_KEY',
  'SUPABASE_SERVICE_ROLE_KEY',
  'NEXT_PUBLIC_SUPABASE_ANON_KEY',
];

beforeEach(() => {
  for (const key of ENV_KEYS) vi.stubEnv(key, undefined);
  rpc.mockReset();
  createClient.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('submitAssessment', () => {
  it('calls submit_assessment_lead through the secret-key admin client', async () => {
    vi.stubEnv('SUPABASE_URL', 'https://example.supabase.co');
    vi.stubEnv('SUPABASE_SECRET_KEY', 'test-secret');
    rpc.mockResolvedValue({ error: null });
    const { submitAssessment } = await import('@/app/actions/submit-assessment');

    const result = await submitAssessment({
      name: ' Ada ',
      email: ' Ada@Example.com ',
      company: ' Acme ',
      role: 'QA',
      quizScore: 0,
    });

    expect(result).toEqual({ success: true });
    expect(createClient).toHaveBeenCalledWith('https://example.supabase.co', 'test-secret', {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    });
    expect(rpc).toHaveBeenCalledWith('submit_assessment_lead', {
      payload: {
        name: 'Ada',
        email: 'ada@example.com',
        company: 'Acme',
        role: 'QA',
        facility_count: null,
        phone: null,
        annual_revenue: null,
        current_system: null,
        biggest_retailer: null,
        compliance_deadline: null,
        recent_fda_inspection: null,
        product_categories: null,
        quiz_score: 0,
        quiz_grade: null,
        quiz_answers: null,
        tool_inputs: null,
        source: 'unknown',
        utm_source: null,
        utm_medium: null,
        utm_campaign: null,
        referrer: null,
      },
    });
  });

  it('returns the generic error when the admin client is not configured', async () => {
    const { submitAssessment } = await import('@/app/actions/submit-assessment');
    vi.spyOn(console, 'error').mockImplementation(() => {});

    const result = await submitAssessment({ name: 'Ada', email: 'ada@example.com', company: 'Acme', role: '' });

    expect(result).toEqual({ success: false, error: 'Something went wrong. Please try again.' });
    expect(rpc).not.toHaveBeenCalled();
  });
});

describe('createSupabaseAdminClient', () => {
  it('throws without echoing configured values when the key is missing', async () => {
    vi.stubEnv('SUPABASE_URL', 'https://leaky.supabase.co');
    const { createSupabaseAdminClient } = await import('@/lib/supabase/admin');

    expect(() => createSupabaseAdminClient()).toThrow('Supabase admin client is not configured.');
    expect(() => createSupabaseAdminClient()).not.toThrow(/leaky/);
  });

  it('never falls back to the public anon key', async () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co');
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'public-anon');
    const { createSupabaseAdminClient } = await import('@/lib/supabase/admin');

    expect(() => createSupabaseAdminClient()).toThrow();
    expect(createClient).not.toHaveBeenCalled();
  });

  it('falls back to SUPABASE_SERVICE_ROLE_KEY and NEXT_PUBLIC_SUPABASE_URL', async () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co');
    vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'legacy-service-role');
    const { createSupabaseAdminClient } = await import('@/lib/supabase/admin');

    createSupabaseAdminClient();

    expect(createClient).toHaveBeenCalledWith('https://example.supabase.co', 'legacy-service-role', expect.any(Object));
  });
});
