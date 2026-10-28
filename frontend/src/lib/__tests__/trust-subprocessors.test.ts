import { describe, expect, it } from 'vitest';
import {
  TRUST_SUBPROCESSORS,
  type TrustSubprocessor,
} from '../trust-subprocessors';

const IN_PRODUCTION_NAMES = [
  'Supabase',
  'Railway',
  'Vercel',
  'Sentry',
  'Stripe',
  'PostHog',
  'Resend',
  'TypeSafe AI',
  'Cloudflare R2',
] as const;

const NOT_IN_PRODUCTION_NAMES = [
  'OpenAI',
  'Google Cloud Vertex AI',
  'LlamaCloud',
] as const;

describe('TRUST_SUBPROCESSORS', () => {
  it('includes every required vendor exactly once', () => {
    const names = TRUST_SUBPROCESSORS.map((sp) => sp.name);
    for (const name of [...IN_PRODUCTION_NAMES, ...NOT_IN_PRODUCTION_NAMES]) {
      expect(names.filter((n) => n === name)).toHaveLength(1);
    }
  });

  it('marks OpenAI, Vertex, and LlamaCloud as not_in_production', () => {
    for (const name of NOT_IN_PRODUCTION_NAMES) {
      const row = TRUST_SUBPROCESSORS.find((sp) => sp.name === name);
      expect(row?.availability).toBe('not_in_production');
    }
  });

  it('does not use where_configured for vendors that are not in production', () => {
    for (const name of NOT_IN_PRODUCTION_NAMES) {
      const row = TRUST_SUBPROCESSORS.find((sp) => sp.name === name);
      expect(row?.availability).not.toBe('where_configured');
    }
  });

  it('uses the exact LlamaCloud availabilityLabel from diligence steering', () => {
    const llama = TRUST_SUBPROCESSORS.find((sp) => sp.name === 'LlamaCloud');
    expect(llama?.availabilityLabel).toBe(
      'available where configured; not enabled in production as of Oct 28, 2026',
    );
  });

  it('uses the Legal not-in-production label for OpenAI and Vertex', () => {
    for (const name of ['OpenAI', 'Google Cloud Vertex AI'] as const) {
      const row = TRUST_SUBPROCESSORS.find((sp) => sp.name === name);
      expect(row?.availabilityLabel).toBe(
        'Not used in production; may be enabled only after notice',
      );
    }
  });

  it('exposes region and transferMechanism fields on every row', () => {
    for (const sp of TRUST_SUBPROCESSORS) {
      expect(sp).toHaveProperty('region');
      expect(sp).toHaveProperty('transferMechanism');
      expect(typeof sp.region).toBe('string');
      expect(typeof sp.transferMechanism).toBe('string');
    }
  });

  it('keeps availabilityLabel free of en/em dashes', () => {
    for (const sp of TRUST_SUBPROCESSORS) {
      expect(sp.availabilityLabel).not.toMatch(/[\u2013\u2014]/);
      expect(sp.purpose).not.toMatch(/[\u2013\u2014]/);
      expect(sp.dataProcessed).not.toMatch(/[\u2013\u2014]/);
      expect(sp.location).not.toMatch(/[\u2013\u2014]/);
      expect(sp.region).not.toMatch(/[\u2013\u2014]/);
      expect(sp.transferMechanism).not.toMatch(/[\u2013\u2014]/);
    }
  });

  it('requires non-empty required display fields', () => {
    for (const sp of TRUST_SUBPROCESSORS as TrustSubprocessor[]) {
      expect(sp.name.length).toBeGreaterThan(0);
      expect(sp.purpose.length).toBeGreaterThan(0);
      expect(sp.dataProcessed.length).toBeGreaterThan(0);
      expect(sp.location.length).toBeGreaterThan(0);
      expect(sp.link.startsWith('https://')).toBe(true);
      expect(sp.availabilityLabel.length).toBeGreaterThan(0);
    }
  });
});
