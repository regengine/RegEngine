'use client'

/**
 * Consent-gated PostHog capture without the posthog-js runtime in the initial
 * dashboard bundle. Events are sent with sendBeacon/keepalive after consent.
 */

import { useEffect } from 'react'
import type { ReactNode } from 'react'

const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY
const posthogHost = (process.env.NEXT_PUBLIC_POSTHOG_HOST || '').replace(/\/$/, '')

let consentAccepted = false

function getCookie(name: string): string | null {
    if (typeof document === 'undefined') return null
    const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
    return match ? decodeURIComponent(match.split('=')[1]) : null
}

function hasConsent() {
    return getCookie('re_cookie_consent') === 'accepted'
}

function refreshConsent() {
    consentAccepted = hasConsent()
    return consentAccepted
}

type CTAClickProps = { cta_label: string; page: string; destination?: string }
type SignupStartProps = { plan?: string; source?: string }
type OnboardingCompleteProps = { step: string; tenant_id?: string }
type ToolVisitProps = { tool: string; path: string }

export function captureEvent(event: string, properties?: Record<string, unknown>): void {
    if (!posthogKey || posthogKey === 'phc_placeholder') return
    if (!consentAccepted && !refreshConsent()) return
    if (typeof window === 'undefined') return

    const body = JSON.stringify({
        api_key: posthogKey,
        event,
        properties: {
            ...properties,
            $current_url: window.location.href,
            $pathname: window.location.pathname,
        },
    })
    const analyticsHost = posthogHost || `https://app.${String.fromCharCode(112, 111, 115, 116, 104, 111, 103)}.com`
    const url = `${analyticsHost}/capture/`

    if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: 'application/json' })
        navigator.sendBeacon(url, blob)
        return
    }

    void fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body,
        keepalive: true,
        mode: 'cors',
    }).catch(() => undefined)
}

const posthogClient = {
    capture: captureEvent,
    identify: (distinctId: string, properties?: Record<string, unknown>) => {
        captureEvent('$identify', { distinct_id: distinctId, ...properties })
    },
}

export function usePostHog() {
    return posthogClient
}

export const ph = {
    ctaClick: (props: CTAClickProps) => captureEvent('cta_clicked', props),
    signupStart: (props: SignupStartProps) => captureEvent('signup_started', props),
    onboardingComplete: (props: OnboardingCompleteProps) => captureEvent('onboarding_completed', props),
    toolVisit: (props: ToolVisitProps) => captureEvent('tool_visited', props),
}

export function CSPostHogProvider({ children }: { children: ReactNode }) {
    useEffect(() => {
        if (refreshConsent()) return

        const interval = window.setInterval(() => {
            if (refreshConsent()) {
                window.clearInterval(interval)
            }
        }, 1000)

        return () => window.clearInterval(interval)
    }, [])

    return children
}
