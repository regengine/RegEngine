'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import FSMAChecklist from '@/components/fsma-checklist';
import { FSMA_204_DEADLINE_ISO, daysUntilFSMA204 } from '@/lib/fsma-tools-data';
import { EmailGate } from '@/components/tools/EmailGate';

import { T, useScrollReveal, useTrackEvent, TRACE_NODES_FORWARD, TRACE_NODES_BACKWARD } from './components/constants';
import ScrollProgressBar from './components/ScrollProgressBar';
import StickyCTA from './components/StickyCTA';
import ExitIntentPopup from './components/ExitIntentPopup';
import HeroSection from './components/HeroSection';
import UrgencyBanner from './components/UrgencyBanner';
import ComplianceTimeline from './components/ComplianceTimeline';
import TraceDemo from './components/TraceDemo';
import BeforeAfterComparison from './components/BeforeAfterComparison';
import RiskCalculator from './components/RiskCalculator';
import PricingSection from './components/PricingSection';
import FounderCredibility from './components/FounderCredibility';
import AssessmentForm from './components/AssessmentForm';
import CompetitorComparison from './components/CompetitorComparison';
import FaqAccordion from './components/FaqAccordion';
import IntegrationsGrid from './components/IntegrationsGrid';
import TrustBadges from './components/TrustBadges';
import PageStyles from './components/PageStyles';

/* ═════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═════════════════════════════════════════════════════════════ */
export default function RetailerSuppliersPage() {
    const [email, setEmail] = useState('');
    const [companyName, setCompanyName] = useState('');
    const [submitted, setSubmitted] = useState(false);

    // Risk calculator state
    const [annualRevenue, setAnnualRevenue] = useState(25);
    const [retailerPercent, setRetailerPercent] = useState(30);

    // Trace animation
    const [traceStep, setTraceStep] = useState(-1);
    const [traceComplete, setTraceComplete] = useState(false);
    const [traceStarted, setTraceStarted] = useState(false);
    const [traceDirection, setTraceDirection] = useState<'forward' | 'backward'>('forward');
    const traceRef = useRef<HTMLDivElement>(null);
    const traceNodes = traceDirection === 'forward' ? TRACE_NODES_FORWARD : TRACE_NODES_BACKWARD;

    // Scroll reveals
    const timeline = useScrollReveal();
    const trace = useScrollReveal();
    const comparison = useScrollReveal();
    const riskCalc = useScrollReveal();
    const pricing = useScrollReveal();
    const founder = useScrollReveal();
    const faqReveal = useScrollReveal();
    const competitorReveal = useScrollReveal();
    const integrationsReveal = useScrollReveal();

    // Countdown
    const [daysCount, setDaysCount] = useState(daysUntilFSMA204);
    const heroRef = useRef<HTMLDivElement>(null);

    // Sticky CTA
    const [showSticky, setShowSticky] = useState(false);

    // Scroll progress
    const [scrollProgress, setScrollProgress] = useState(0);

    // Exit intent
    const [showExitIntent, setShowExitIntent] = useState(false);
    const exitShownRef = useRef(false);

    // FAQ accordion
    const [openFaq, setOpenFaq] = useState<number | null>(null);

    // Analytics tracking helper
    const trackEvent = useTrackEvent();

    // Sticky CTA: show after scrolling past hero
    useEffect(() => {
        const handleScroll = () => {
            setShowSticky(window.scrollY > 600);
            // Scroll progress
            const h = document.documentElement.scrollHeight - window.innerHeight;
            setScrollProgress(h > 0 ? (window.scrollY / h) * 100 : 0);
        };
        window.addEventListener('scroll', handleScroll, { passive: true });
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    // Exit intent detection — desktop only (no accidental triggers on touch scroll)
    useEffect(() => {
        const isTouchDevice = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
        if (isTouchDevice) return;

        const handleMouseLeave = (e: MouseEvent) => {
            if (e.clientY < 10 && !exitShownRef.current && !submitted) {
                exitShownRef.current = true;
                setShowExitIntent(true);
                trackEvent('exit_intent_shown');
            }
        };
        document.addEventListener('mouseleave', handleMouseLeave);
        return () => document.removeEventListener('mouseleave', handleMouseLeave);
    }, [submitted, trackEvent]);

    useEffect(() => {
        // Refresh the count on mount (handles SSR → client hydration)
        setDaysCount(daysUntilFSMA204());
    }, []);

    // Trace animation auto-play when visible
    const startTrace = useCallback(() => {
        if (traceStarted) return;
        setTraceStarted(true);
        setTraceStep(-1);
        setTraceComplete(false);

        const nodes = traceDirection === 'forward' ? TRACE_NODES_FORWARD : TRACE_NODES_BACKWARD;
        nodes.forEach((_, i) => {
            setTimeout(() => {
                setTraceStep(i);
                if (i === nodes.length - 1) {
                    setTimeout(() => setTraceComplete(true), 600);
                }
            }, (i + 1) * 700);
        });
    }, [traceStarted, traceDirection]);

    useEffect(() => {
        if (trace.visible) startTrace();
    }, [trace.visible, startTrace]);

    const handleAssessment = async (e: React.FormEvent) => {
        e.preventDefault();
        if (email && companyName) {
            const payload = { email, companyName, date: new Date().toISOString() };

            try {
                const res = await fetch('/api/v1/assessments/retailer-readiness', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) throw new Error(`API responded ${res.status}`);
            } catch {
                // Fallback: persist locally so the submission is not lost
                localStorage.setItem('retailer_supplier_lead', JSON.stringify(payload));
            }

            trackEvent('assessment_submitted', { email, companyName });
            setSubmitted(true);
        }
    };

    const atRisk = ((annualRevenue * 1_000_000) * (retailerPercent / 100));
    const monthlyRisk = Math.round(atRisk / 12);

    return (
        <EmailGate toolName="retailer-readiness">
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: "'Instrument Sans', -apple-system, sans-serif" }}>
            <ScrollProgressBar scrollProgress={scrollProgress} />

            <StickyCTA showSticky={showSticky} daysCount={daysCount} trackEvent={trackEvent} />

            <ExitIntentPopup
                showExitIntent={showExitIntent}
                setShowExitIntent={setShowExitIntent}
                trackEvent={trackEvent}
            />

            {/* Noise overlay */}
            <div style={{
                position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1, opacity: 0.015,
                backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
            }} />

            <UrgencyBanner />

            <HeroSection heroRef={heroRef} daysCount={daysCount} />

            <ComplianceTimeline revealRef={timeline.ref} visible={timeline.visible} />

            <TraceDemo
                revealRef={trace.ref}
                visible={trace.visible}
                traceRef={traceRef}
                traceDirection={traceDirection}
                setTraceDirection={setTraceDirection}
                traceNodes={traceNodes}
                traceStep={traceStep}
                traceComplete={traceComplete}
                setTraceStarted={setTraceStarted}
                setTraceStep={setTraceStep}
                setTraceComplete={setTraceComplete}
                startTrace={startTrace}
                trackEvent={trackEvent}
            />

            <BeforeAfterComparison revealRef={comparison.ref} visible={comparison.visible} />

            <RiskCalculator
                revealRef={riskCalc.ref}
                visible={riskCalc.visible}
                annualRevenue={annualRevenue}
                setAnnualRevenue={setAnnualRevenue}
                retailerPercent={retailerPercent}
                setRetailerPercent={setRetailerPercent}
                atRisk={atRisk}
                monthlyRisk={monthlyRisk}
            />

            <FSMAChecklist />

            <PricingSection revealRef={pricing.ref} visible={pricing.visible} />

            <FounderCredibility revealRef={founder.ref} visible={founder.visible} />

            <AssessmentForm
                email={email}
                setEmail={setEmail}
                companyName={companyName}
                setCompanyName={setCompanyName}
                submitted={submitted}
                handleAssessment={handleAssessment}
            />

            <CompetitorComparison revealRef={competitorReveal.ref} visible={competitorReveal.visible} />

            <FaqAccordion
                revealRef={faqReveal.ref}
                visible={faqReveal.visible}
                openFaq={openFaq}
                setOpenFaq={setOpenFaq}
                trackEvent={trackEvent}
            />

            <IntegrationsGrid revealRef={integrationsReveal.ref} visible={integrationsReveal.visible} />

            <TrustBadges />

            <PageStyles />

            {/* Bottom spacer for sticky CTA */}
            <div style={{ height: 80 }} />
        </div>
        </EmailGate>
    );
}
