'use client'

/**
 * PostHog provider with cookie-consent gating (#566).
 *
 * PostHog is only initialised after the user has explicitly accepted cookies
 * via the consent banner (re_cookie_consent=accepted). We also expose
 * captureEvent() for CTA-click, signup-start, onboarding-completion, and
 * tool-visit events — callers check isReady before firing.
 */

import { useEffect, useState } from 'react'
import posthog from 'posthog-js'
import { PostHogProvider } from 'posthog-js/react'

const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY

/** Return the current value of a named cookie, or null if absent. */
function getCookie(name: string): string | null {
    if (typeof document === 'undefined') return null
    const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
    return match ? decodeURIComponent(match.split('=')[1]) : null
}

let _initialized = false

/** Initialise PostHog if consent has been given and it is not yet running. */
function maybeInit(): boolean {
    if (_initialized) return true
    if (!posthogKey || posthogKey === 'phc_placeholder') return false
    if (getCookie('re_cookie_consent') !== 'accepted') return false

    posthog.init(posthogKey, {
        api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://app.posthog.com',
        person_profiles: 'identified_only',
        capture_pageview: false, // Managed manually via Next.js router events
        loaded: () => { _initialized = true },
    })
    _initialized = true
    return true
}

// ── Typed event helpers ───────────────────────────────────────────────���──────

type CTAClickProps = { cta_label: string; page: string; destination?: string }
type SignupStartProps = { plan?: string; source?: string }
type OnboardingCompleteProps = { step: string; tenant_id?: string }
type ToolVisitProps = { tool: string; path: string }

/** Fire a PostHog event — silently no-ops if consent not given or key absent. */
export function captureEvent(event: string, properties?: Record<string, unknown>): void {
    if (!_initialized && !maybeInit()) return
    posthog.capture(event, properties)
}

export const ph = {
    ctaClick: (props: CTAClickProps) => captureEvent('cta_clicked', props),
    signupStart: (props: SignupStartProps) => captureEvent('signup_started', props),
    onboardingComplete: (props: OnboardingCompleteProps) => captureEvent('onboarding_completed', props),
    toolVisit: (props: ToolVisitProps) => captureEvent('tool_visited', props),
}

// ── Provider ─────────────────────────────────────────────────────────���──────

export function CSPostHogProvider({ children }: { children: React.ReactNode }) {
    const [ready, setReady] = useState(false)

    useEffect(() => {
        // Attempt init on mount; if consent was already given this will succeed.
        const ok = maybeInit()
        if (ok) { setReady(true); return }

        // Otherwise, poll for the cookie being set (consent banner accepted).
        const interval = setInterval(() => {
            if (maybeInit()) {
                setReady(true)
                clearInterval(interval)
            }
        }, 1000)

        return () => clearInterval(interval)
    }, [])

    // Always render the provider tree — events simply queue until init runs.
    void ready // suppress unused-var warning
    return <PostHogProvider client={posthog}>{children}</PostHogProvider>
}
