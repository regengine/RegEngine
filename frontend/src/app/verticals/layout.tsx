'use client';

import { usePathname } from 'next/navigation';
import { ReactNode, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Lock, Mail, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';

export default function VerticalsLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();
    const [email, setEmail] = useState('');
    const [submitted, setSubmitted] = useState(false);

    // Only allow food-safety and fsma related pages
    const isAllowed = pathname?.includes('/food-safety') || pathname?.includes('/fsma');
    const verticalMatch = pathname?.match(/\/verticals\/([^/]+)/);
    const verticalName = verticalMatch ? verticalMatch[1].charAt(0).toUpperCase() + verticalMatch[1].slice(1) : 'Industry';

    if (!isAllowed && pathname?.startsWith('/verticals')) {
        return (
            <div className="min-h-screen bg-gradient-to-b flex flex-col" style={{ background: 'var(--re-surface-base)' }}>
                <div className="flex-1 flex items-center justify-center py-20 px-4">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="max-w-md w-full border rounded-2xl shadow-2xl overflow-hidden"
                        style={{ background: 'var(--re-surface-elevated)', borderColor: 'var(--re-border-default)' }}
                    >
                        <div className="p-8 text-center space-y-6 flex flex-col items-center">
                            <div className="w-16 h-16 rounded-full flex items-center justify-center mb-2" style={{ background: 'rgba(56, 189, 248, 0.1)' }}>
                                <Lock className="w-8 h-8" style={{ color: 'var(--re-brand)' }} />
                            </div>

                            <div>
                                <h1 className="text-2xl font-bold mb-3" style={{ color: 'var(--re-text-primary)' }}>
                                    {verticalName} Vertical Locked
                                </h1>
                                <p className="text-sm leading-relaxed" style={{ color: 'var(--re-text-secondary)' }}>
                                    The RegEngine {verticalName} compliance suite is currently in private beta context.
                                    Enter your email to join the waitlist and get notified when early market access opens.
                                </p>
                            </div>

                            {submitted ? (
                                <motion.div
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    className="p-4 rounded-xl w-full border"
                                    style={{ background: 'var(--re-success-muted)', borderColor: 'var(--re-success)', color: 'var(--re-success)' }}
                                >
                                    <p className="text-sm font-medium">You're on the list! We'll be in touch soon.</p>
                                </motion.div>
                            ) : (
                                <form
                                    className="w-full space-y-3 mt-4"
                                    onSubmit={(e) => {
                                        e.preventDefault();
                                        if (email) setSubmitted(true);
                                    }}
                                >
                                    <div className="relative">
                                        <Mail className="absolute left-3 top-2.5 h-4 w-4" style={{ color: 'var(--re-text-muted)' }} />
                                        <Input
                                            type="email"
                                            placeholder="Enter your work email"
                                            className="pl-9"
                                            style={{ background: 'var(--re-surface-base)', borderColor: 'var(--re-border-default)', color: 'var(--re-text-primary)' }}
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            required
                                        />
                                    </div>
                                    <Button type="submit" className="w-full gap-2 text-white" style={{ background: 'var(--re-brand)' }}>
                                        Join Waitlist <ArrowRight className="w-4 h-4" />
                                    </Button>
                                </form>
                            )}
                        </div>
                    </motion.div>
                </div>
            </div>
        );
    }

    // Wrap allowed verticals transparently
    return <>{children}</>;
}
