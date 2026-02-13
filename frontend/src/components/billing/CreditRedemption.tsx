'use client';

/**
 * CreditRedemption — Credit code input with validation animation
 *
 * Allows users to enter promo/referral/partner codes during checkout.
 * Shows applied discount and updated balance.
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Gift, Check, X, Sparkles, Loader2, Tag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useRedeemCredit, type RedeemResult } from '@/hooks/use-billing';

interface CreditRedemptionProps {
    onCreditApplied?: (result: RedeemResult) => void;
    compact?: boolean;
}

export function CreditRedemption({ onCreditApplied, compact = false }: CreditRedemptionProps) {
    const [code, setCode] = useState('');
    const [showInput, setShowInput] = useState(false);
    const [lastResult, setLastResult] = useState<RedeemResult | null>(null);
    const redeemMutation = useRedeemCredit();

    const handleRedeem = async () => {
        if (!code.trim()) return;

        try {
            const result = await redeemMutation.mutateAsync({ code: code.trim() });
            setLastResult(result);
            if (result.success) {
                onCreditApplied?.(result);
                setCode('');
            }
        } catch {
            setLastResult({
                success: false,
                amount_cents: 0,
                credit_type: null,
                new_balance_cents: 0,
                message: 'Failed to redeem code. Please try again.',
            });
        }
    };

    // Compact version — just a link to expand
    if (!showInput && compact) {
        return (
            <button
                onClick={() => setShowInput(true)}
                className="flex items-center gap-2 text-sm transition-colors hover:opacity-80 text-re-brand"
            >
                <Tag className="w-4 h-4" />
                Have a promo or referral code?
            </button>
        );
    }

    return (
        <div className="space-y-3">
            {/* Header */}
            {!compact && (
                <div className="flex items-center gap-2">
                    <Gift className="w-5 h-5 text-re-brand" />
                    <h3 className="font-semibold text-sm text-re-text-primary">
                        Apply Credit Code
                    </h3>
                </div>
            )}

            {/* Input row */}
            <div className="flex gap-2">
                <Input
                    placeholder="Enter code (e.g., EARLY2026)"
                    value={code}
                    onChange={(e) => {
                        setCode(e.target.value.toUpperCase());
                        setLastResult(null);
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && handleRedeem()}
                    className="flex-1 font-mono text-sm border-[var(--re-border-default)]"
                    style={{
                        background: 'var(--re-surface-elevated)',
                        color: 'var(--re-text-primary)',
                    }}
                    disabled={redeemMutation.isPending}
                />
                <Button
                    onClick={handleRedeem}
                    disabled={!code.trim() || redeemMutation.isPending}
                    className="font-semibold px-5"
                    style={{
                        background: 'var(--re-brand)',
                        color: 'var(--re-surface-base)',
                    }}
                >
                    {redeemMutation.isPending ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        'Apply'
                    )}
                </Button>
            </div>

            {/* Result feedback */}
            <AnimatePresence mode="wait">
                {lastResult && (
                    <motion.div
                        key={lastResult.success ? 'success' : 'error'}
                        initial={{ opacity: 0, y: -8, height: 0 }}
                        animate={{ opacity: 1, y: 0, height: 'auto' }}
                        exit={{ opacity: 0, y: -8, height: 0 }}
                        className="overflow-hidden"
                    >
                        <div
                            className="flex items-start gap-3 p-3 rounded-lg text-sm"
                            style={{
                                background: lastResult.success
                                    ? 'var(--re-success-muted)'
                                    : 'var(--re-danger-muted)',
                                borderLeft: `3px solid ${lastResult.success ? 'var(--re-success)' : 'var(--re-danger)'}`,
                            }}
                        >
                            {lastResult.success ? (
                                <Sparkles className="w-4 h-4 mt-0.5 shrink-0 text-re-success" />
                            ) : (
                                <X className="w-4 h-4 mt-0.5 shrink-0 text-re-danger" />
                            )}
                            <div>
                                <p
                                    className="font-medium"
                                    style={{
                                        color: lastResult.success
                                            ? 'var(--re-success)'
                                            : 'var(--re-danger)',
                                    }}
                                >
                                    {lastResult.success ? 'Credit Applied!' : 'Code Not Valid'}
                                </p>
                                <p className="text-re-text-secondary">{lastResult.message}</p>
                                {lastResult.success && (
                                    <p className="mt-1 font-semibold text-re-success">
                                        +${(lastResult.amount_cents / 100).toFixed(2)} added to your balance
                                    </p>
                                )}
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Available codes hint */}
            <div className="flex flex-wrap gap-2 mt-1">
                {['EARLY2026', 'LAUNCH50', 'REFER500'].map((hint) => (
                    <button
                        key={hint}
                        onClick={() => {
                            setCode(hint);
                            setLastResult(null);
                        }}
                        className="px-2 py-0.5 rounded text-xs font-mono transition-opacity hover:opacity-100 opacity-50"
                        style={{
                            background: 'var(--re-surface-elevated)',
                            color: 'var(--re-text-muted)',
                            border: '1px solid var(--re-border-default)',
                        }}
                    >
                        {hint}
                    </button>
                ))}
            </div>
        </div>
    );
}
