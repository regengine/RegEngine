'use client';

import { useState } from 'react';
import { ArrowRight, CheckCircle2 } from 'lucide-react';

export default function AlphaSignupForm() {
    const [email, setEmail] = useState('');
    const [company, setCompany] = useState('');
    const [role, setRole] = useState('');
    const [revenueRange, setRevenueRange] = useState('');
    const [supplierCount, setSupplierCount] = useState('');
    const [currentProcess, setCurrentProcess] = useState('');
    const [champion, setChampion] = useState('');
    const [mobileUse, setMobileUse] = useState('');
    const [submitted, setSubmitted] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email) return;
        setIsSubmitting(true);
        setError('');
        try {
            const res = await fetch('/api/alpha-signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email, company, role,
                    revenue_range: revenueRange,
                    supplier_count: supplierCount,
                    current_process: currentProcess,
                    champion,
                    mobile_use: mobileUse,
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data.error || 'Something went wrong. Please try again.');
                setIsSubmitting(false);
                return;
            }
            setSubmitted(true);
        } catch {
            setError('Network error. Please try again.');
        } finally {
            setIsSubmitting(false);
        }
    };

    if (submitted) {
        return (
            <div className="text-center py-8 sm:py-10">
                <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-[var(--re-brand)]/10 flex items-center justify-center mx-auto mb-4">
                    <CheckCircle2 className="w-8 h-8 sm:w-10 sm:h-10 text-[var(--re-brand)]" />
                </div>
                <h3 className="text-lg sm:text-xl font-bold text-[var(--re-text-primary)] mb-2">
                    Application received
                </h3>
                <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[340px] mx-auto">
                    We&apos;ll review your application and reach out within 48 hours to schedule a fit-check call.
                </p>
                <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4 text-left space-y-3">
                    <p className="text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)]">What happens next</p>
                    <div className="flex items-start gap-3">
                        <span className="w-5 h-5 rounded-full bg-[var(--re-brand)]/10 text-[var(--re-brand)] text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
                        <p className="text-[13px] text-[var(--re-text-secondary)]">We review your application against our 3-criteria framework (typically within 24 hrs)</p>
                    </div>
                    <div className="flex items-start gap-3">
                        <span className="w-5 h-5 rounded-full bg-[var(--re-brand)]/10 text-[var(--re-brand)] text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
                        <p className="text-[13px] text-[var(--re-text-secondary)]">If it&apos;s a fit, we schedule a 30-min call to scope your integration</p>
                    </div>
                    <div className="flex items-start gap-3">
                        <span className="w-5 h-5 rounded-full bg-[var(--re-brand)]/10 text-[var(--re-brand)] text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
                        <p className="text-[13px] text-[var(--re-text-secondary)]">You get access to the platform with founding pricing locked in for life</p>
                    </div>
                </div>
            </div>
        );
    }

    const inputClass = "w-full px-4 py-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-[var(--re-text-primary)] text-sm placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:border-[var(--re-brand)] focus:ring-1 focus:ring-[var(--re-brand)]/20 transition-colors min-h-[44px]";
    const selectClass = `${inputClass} appearance-none cursor-pointer`;
    const labelClass = "text-[13px] font-medium text-[var(--re-text-secondary)] block mb-1.5";
    const sectionLabel = "text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mt-4 mb-2";

    return (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* ── Basics ── */}
            <div>
                <label htmlFor="email" className={labelClass}>Work email *</label>
                <input
                    id="email" type="email" required
                    value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                    className={inputClass}
                />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label htmlFor="company" className={labelClass}>Company *</label>
                    <input
                        id="company" type="text" required
                        value={company} onChange={(e) => setCompany(e.target.value)}
                        placeholder="Company name"
                        className={inputClass}
                    />
                </div>
                <div>
                    <label htmlFor="role" className={labelClass}>Your role *</label>
                    <input
                        id="role" type="text" required
                        value={role} onChange={(e) => setRole(e.target.value)}
                        placeholder="VP Operations, QA Manager, etc."
                        className={inputClass}
                    />
                </div>
            </div>

            {/* ── Representativeness ── */}
            <p className={sectionLabel}>About your operation</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label htmlFor="revenueRange" className={labelClass}>Annual revenue range</label>
                    <select
                        id="revenueRange"
                        value={revenueRange} onChange={(e) => setRevenueRange(e.target.value)}
                        className={selectClass}
                    >
                        <option value="">Select range</option>
                        <option value="under-1m">Under $1M</option>
                        <option value="1m-10m">$1M {'\u2013'} $10M</option>
                        <option value="10m-50m">$10M {'\u2013'} $50M</option>
                        <option value="50m-250m">$50M {'\u2013'} $250M</option>
                        <option value="250m-plus">$250M+</option>
                    </select>
                </div>
                <div>
                    <label htmlFor="supplierCount" className={labelClass}>Suppliers / facilities managed</label>
                    <select
                        id="supplierCount"
                        value={supplierCount} onChange={(e) => setSupplierCount(e.target.value)}
                        className={selectClass}
                    >
                        <option value="">Select count</option>
                        <option value="1-5">1 {'\u2013'} 5</option>
                        <option value="6-20">6 {'\u2013'} 20</option>
                        <option value="21-50">21 {'\u2013'} 50</option>
                        <option value="50-plus">50+</option>
                    </select>
                </div>
            </div>

            {/* ── Urgency ── */}
            <p className={sectionLabel}>Current traceability approach</p>
            <div>
                <label htmlFor="currentProcess" className={labelClass}>
                    How do you handle traceability today? What broke?
                </label>
                <textarea
                    id="currentProcess"
                    value={currentProcess} onChange={(e) => setCurrentProcess(e.target.value)}
                    placeholder="Spreadsheets, manual lot logs, another tool, nothing yet..."
                    rows={2}
                    className={`${inputClass} resize-none`}
                />
            </div>

            {/* ── Capacity ── */}
            <p className={sectionLabel}>Implementation readiness</p>
            <div>
                <label htmlFor="champion" className={labelClass}>
                    Who will own the rollout? (name + role + hours/week)
                </label>
                <input
                    id="champion" type="text"
                    value={champion} onChange={(e) => setChampion(e.target.value)}
                    placeholder="Jane Smith, QA Lead, ~3 hrs/week"
                    className={inputClass}
                />
            </div>
            <div>
                <label htmlFor="mobileUse" className={labelClass}>
                    Do your teams use phones/tablets in receiving or shipping?
                </label>
                <select
                    id="mobileUse"
                    value={mobileUse} onChange={(e) => setMobileUse(e.target.value)}
                    className={selectClass}
                >
                    <option value="">Select</option>
                    <option value="yes-daily">Yes, daily</option>
                    <option value="yes-sometimes">Yes, sometimes</option>
                    <option value="no-desktop-only">No, desktop only</option>
                    <option value="planning-to">Planning to start</option>
                </select>
            </div>

            {error && (
                <p className="text-[13px] text-red-500">{error}</p>
            )}
            <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-2 px-6 py-3.5 rounded-xl bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold text-sm transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:scale-[0.97] active:translate-y-0 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 min-h-[48px]"
            >
                {isSubmitting ? 'Submitting...' : 'Apply to Become a Founding Design Partner'}
                {!isSubmitting && <ArrowRight className="w-4 h-4" />}
            </button>
            <p className="text-[11px] text-[var(--re-text-disabled)] text-center">
                We review every application within 48 hours. Only fields marked * are required.
            </p>
        </form>
    );
}
