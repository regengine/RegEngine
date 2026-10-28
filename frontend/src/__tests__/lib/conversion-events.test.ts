import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { track } from '@vercel/analytics';
import {
  filterConversionAnalyticsEvent,
  getConversionAttribution,
  isInternalAnalyticsSession,
  setConversionAnalyticsEnabled,
  trackConversionEvent,
  trackToolRunStarted,
} from '@/lib/conversion-events';

import { captureEvent } from '@/lib/posthog-provider';

vi.mock('@vercel/analytics', () => ({ track: vi.fn() }));
vi.mock('@/lib/posthog-provider', () => ({ captureEvent: vi.fn() }));

beforeEach(() => {
  window.history.replaceState({}, '', '/tools/ftl-checker');
  document.cookie = 're_cookie_consent=accepted; path=/';
  setConversionAnalyticsEnabled(true);
});

afterEach(() => {
  setConversionAnalyticsEnabled(false);
  document.cookie = 're_cookie_consent=; max-age=0; path=/';
  window.sessionStorage.removeItem('re_utm');
  window.localStorage.removeItem('re_internal');
  vi.clearAllMocks();
});

describe('conversion event privacy', () => {
  it('does not forward email, name, or free text, including caller-supplied common fields', () => {
    trackConversionEvent('tool_run_started', {
      tool: 'ftl-checker',
      email: 'person@example.com',
      name: 'Person Name',
      message: 'private free text',
      path: '/contact?email=person@example.com',
      utm_source: 'person@example.com',
      form: 'email_gate',
    });

    expect(track).toHaveBeenCalledTimes(1);
    expect(track).toHaveBeenCalledWith('tool_run_started', {
      path: '/tools/ftl-checker',
      tool: 'ftl-checker',
    });
  });

  it('drops invalid enum values, labels, grades, and success error codes', () => {
    trackConversionEvent('readiness_assessment_submit', {
      outcome: 'maybe',
      error_code: 'raw backend message',
      grade: 'A+',
    });
    expect(track).toHaveBeenLastCalledWith('readiness_assessment_submit', {
      path: '/tools/ftl-checker',
    });

    trackConversionEvent('email_capture_submit', {
      form: true, step: 7, outcome: 'error', error_code: 'server',
    });
    expect(track).toHaveBeenLastCalledWith('email_capture_submit', {
      path: '/tools/ftl-checker', outcome: 'error', error_code: 'server',
    });

    trackConversionEvent('book_call_click', {
      placement: 'Jane Smith', tool: 'person@example.com',
    });
    expect(track).toHaveBeenLastCalledWith('book_call_click', {
      path: '/tools/ftl-checker',
    });

    trackConversionEvent('contact_form_submit', { outcome: 'success', error_code: 'server' });
    expect(track).toHaveBeenLastCalledWith('contact_form_submit', {
      path: '/tools/ftl-checker',
      outcome: 'success',
    });

    trackConversionEvent('email_capture_submit', {
      form: 'email_gate', step: 'verify', outcome: 'error', error_code: 'unavailable',
    });
    expect(track).toHaveBeenLastCalledWith('email_capture_submit', {
      path: '/tools/ftl-checker', form: 'email_gate', step: 'verify', outcome: 'error',
    });
  });

  it('never calls track before consent or when Analytics is not mounted', () => {
    setConversionAnalyticsEnabled(false);
    trackToolRunStarted('ftl-checker');
    setConversionAnalyticsEnabled(true);
    document.cookie = 're_cookie_consent=declined; path=/';
    trackToolRunStarted('ftl-checker');
    expect(track).not.toHaveBeenCalled();
  });

  it('does not interrupt a tool when the analytics client throws', () => {
    vi.mocked(track).mockImplementationOnce(() => { throw new Error('analytics unavailable'); });
    expect(() => trackToolRunStarted('ftl-checker')).not.toThrow();
  });

  it('uses current UTM values and the first session values as fallback', () => {
    window.history.replaceState({}, '', '/tools/ftl-checker?utm_source=%20Paid_Search%20&utm_medium=CPC');
    expect(getConversionAttribution()).toEqual({ utm_source: 'paid_search', utm_medium: 'cpc' });

    window.history.replaceState({}, '', '/tools/ftl-checker?utm_campaign=Launch');
    trackToolRunStarted('ftl-checker');
    expect(track).toHaveBeenLastCalledWith('tool_run_started', {
      path: '/tools/ftl-checker',
      utm_source: 'paid_search',
      utm_medium: 'cpc',
      utm_campaign: 'launch',
      tool: 'ftl-checker',
    });
    expect(JSON.parse(window.sessionStorage.getItem('re_utm') ?? '{}')).toEqual({
      utm_source: 'paid_search', utm_medium: 'cpc', utm_campaign: 'launch',
    });
  });

  it('keeps spaced UTM values for lead rows but omits them from events', () => {
    window.history.replaceState({}, '', '/tools/ftl-checker?utm_source=%20Paid%20Search%20');
    expect(getConversionAttribution()).toEqual({ utm_source: 'paid search' });

    window.history.replaceState({}, '', '/tools/ftl-checker');
    expect(getConversionAttribution()).toEqual({ utm_source: 'paid search' });
    trackToolRunStarted('ftl-checker');
    expect(track).toHaveBeenLastCalledWith('tool_run_started', {
      path: '/tools/ftl-checker', tool: 'ftl-checker',
    });
  });

  it('omits name, email, and phone-like UTM values and truncates permitted slugs', () => {
    window.history.replaceState({}, '', `/tools/ftl-checker?utm_source=person%40example.com&utm_medium=Jane%20Smith&utm_campaign=${'A'.repeat(120)}&utm_term=555-123-4567`);
    trackToolRunStarted('ftl-checker');
    expect(track).toHaveBeenLastCalledWith('tool_run_started', {
      path: '/tools/ftl-checker',
      utm_campaign: 'a'.repeat(100),
      tool: 'ftl-checker',
    });

    window.history.replaceState({}, '', '/tools/ftl-checker?utm_source=1234567890&utm_campaign=555-123-4567');
    window.sessionStorage.removeItem('re_utm');
    expect(getConversionAttribution()).toEqual({
      utm_source: '1234567890', utm_campaign: '555-123-4567',
    });
    trackToolRunStarted('ftl-checker');
    expect(track).toHaveBeenLastCalledWith('tool_run_started', {
      path: '/tools/ftl-checker', tool: 'ftl-checker',
    });
  });

  it('omits a path that contains an encoded email', () => {
    window.history.replaceState({}, '', '/tools/person%40example.com');
    trackToolRunStarted('ftl-checker');
    expect(track).toHaveBeenLastCalledWith('tool_run_started', { tool: 'ftl-checker' });
  });
});

describe('marketing Web Analytics filter', () => {
  it('drops authenticated app routes but retains public marketing routes', () => {
    const event = (path: string) => ({ type: 'pageview', url: `https://regengine.co${path}` });
    expect(filterConversionAnalyticsEvent(event('/dashboard'))).toBeNull();
    expect(filterConversionAnalyticsEvent(event('/dashboard/overview'))).toBeNull();
    expect(filterConversionAnalyticsEvent(event('/developer/portal'))).toBeNull();
    expect(filterConversionAnalyticsEvent(event('/reports/monthly'))).toBeNull();
    expect(filterConversionAnalyticsEvent(event('/incidents'))).toBeNull();
    expect(filterConversionAnalyticsEvent(event('/tools/ftl-checker'))).toEqual(event('/tools/ftl-checker'));
    expect(filterConversionAnalyticsEvent(event('/fsma/assessment'))).toEqual(event('/fsma/assessment'));
    expect(filterConversionAnalyticsEvent(event('/developers'))).toEqual(event('/developers'));
    expect(filterConversionAnalyticsEvent(event('/dashboarding'))).toEqual(event('/dashboarding'));
  });

  it('persists and clears the internal-browser marker from URL switches', () => {
    window.history.replaceState({}, '', '/contact?re_internal=1');
    expect(filterConversionAnalyticsEvent({ type: 'pageview', url: 'https://regengine.co/contact' })).toBeNull();
    expect(isInternalAnalyticsSession()).toBe(true);
    expect(window.localStorage.getItem('re_internal')).toBe('1');
    expect(filterConversionAnalyticsEvent({ type: 'event', url: 'https://regengine.co/contact' })).toBeNull();
    trackToolRunStarted('ftl-checker');
    expect(track).not.toHaveBeenCalled();

    window.history.replaceState({}, '', '/contact?re_internal=0');
    expect(isInternalAnalyticsSession()).toBe(false);
    expect(window.localStorage.getItem('re_internal')).toBeNull();
    const pageview = { type: 'pageview', url: 'https://regengine.co/contact' };
    expect(filterConversionAnalyticsEvent(pageview)).toEqual(pageview);
  });
});

describe('conversion events reach PostHog', () => {
  it('forwards tool runs to PostHog even when Vercel Analytics is not mounted', () => {
    setConversionAnalyticsEnabled(false);
    trackToolRunStarted('ftl-checker');
    expect(track).not.toHaveBeenCalled();
    expect(captureEvent).toHaveBeenCalledWith('tool_run_started', {
      path: '/tools/ftl-checker', tool: 'ftl-checker',
    });
  });

  it('sends nothing to PostHog without consent', () => {
    document.cookie = 're_cookie_consent=; max-age=0; path=/';
    trackToolRunStarted('ftl-checker');
    expect(captureEvent).not.toHaveBeenCalled();
  });
});
