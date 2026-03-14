'use client';

import { useState } from 'react';
import { ArrowRight, CheckCircle2 } from 'lucide-react';

export default function AlphaSignupForm() {
    const [email, setEmail] = useState('');
    const [company, setCompany] = useState('');
    const [role, setRole] = useState('');
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
                body: JSON.stringify({ email, company, role }),
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
            <div className="text-center py-10">
                <CheckCircle2 className="w-12 h-12 text-[var(--re-brand)] mx-auto mb-4" />
                <h3 className="text-xl font-bold text-[var(--re-text-primary)] mb-2">
                    Application received
                </h3>
                <p className="text-sm text-[var(--re-text-muted)]">
                    We&apos;ll review your application and reach out within 48 hours.
                </p>
            </div>
        );
    }
    const inputClass = "w-full px-4 py-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-[var(--re-text-primary)] text-sm placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:border-[var(--re-brand)] transition-colors";

    return (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
                <label htmlFor="email" className="text-[13px] font-medium text-[var(--re-text-secondary)] block mb-1.5">
                    Work email *
                </label>
                <input
                    id="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                    className={inputClass}
                />
            </div>
            <div>
                <label htmlFor="company" className="text-[13px] font-medium text-[var(--re-text-secondary)] block mb-1.5">
                    Company
                </label>
                <input
                    id="company"
                    type="text"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="Company name"
                    className={inputClass}
                />
            </div>            <div>
                <label htmlFor="role" className="text-[13px] font-medium text-[var(--re-text-secondary)] block mb-1.5">
                    Role
                </label>
                <input
                    id="role"
                    type="text"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    placeholder="VP Operations, QA Manager, etc."
                    className={inputClass}
                />
            </div>
            {error && (
                <p className="text-[13px] text-red-500">{error}</p>
            )}
            <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-2 px-6 py-3.5 rounded-xl bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold text-sm transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
                {isSubmitting ? 'Submitting...' : 'Apply for Design Partner Access'}
                {!isSubmitting && <ArrowRight className="w-4 h-4" />}
            </button>
        </form>
    );
}