'use client';

import { useState } from 'react';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

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
            <div style={{ textAlign: 'center', padding: '40px 24px' }}>
                <CheckCircle2 style={{ width: 48, height: 48, color: 'var(--re-brand)', margin: '0 auto 16px' }} />
                <h3 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                    Application received
                </h3>
                <p style={{ fontSize: '14px', color: 'var(--re-text-muted)' }}>
                    We&apos;ll review your application and reach out within 48 hours.
                </p>
            </div>
        );
    }

    return (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
                <label htmlFor="email" style={{ fontSize: '13px', fontWeight: 500, color: 'var(--re-text-secondary)', display: 'block', marginBottom: '6px' }}>
                    Work email *
                </label>
                <input
                    id="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                    style={{
                        width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px',
                        color: 'var(--re-text-primary)', fontSize: '14px',
                    }}
                />
            </div>
            <div>
                <label htmlFor="company" style={{ fontSize: '13px', fontWeight: 500, color: 'var(--re-text-secondary)', display: 'block', marginBottom: '6px' }}>
                    Company
                </label>
                <input
                    id="company"
                    type="text"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="Company name"
                    style={{
                        width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px',
                        color: 'var(--re-text-primary)', fontSize: '14px',
                    }}
                />
            </div>
            <div>
                <label htmlFor="role" style={{ fontSize: '13px', fontWeight: 500, color: 'var(--re-text-secondary)', display: 'block', marginBottom: '6px' }}>
                    Role
                </label>
                <input
                    id="role"
                    type="text"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    placeholder="VP Operations, QA Manager, etc."
                    style={{
                        width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px',
                        color: 'var(--re-text-primary)', fontSize: '14px',
                    }}
                />
            </div>
            {error && (
                <p style={{ fontSize: '13px', color: '#ef4444' }}>{error}</p>
            )}
            <Button
                type="submit"
                disabled={isSubmitting}
                style={{
                    width: '100%', background: 'var(--re-brand)', color: '#000',
                    fontWeight: 600, padding: '14px 24px', marginTop: '8px',
                }}
            >
                {isSubmitting ? 'Submitting...' : 'Apply for Design Partner Access'}
                {!isSubmitting && <ArrowRight className="ml-2 w-4 h-4" />}
            </Button>
        </form>
    );
}
