'use client';

/**
 * PlanCard — Reusable pricing tier presentation component
 *
 * Displays tier name, pricing, features, and selection state.
 * Dark glassmorphism design matching RegEngine design system.
 */

import { motion } from 'framer-motion';
import { Check, X, Star, Zap, Rocket, Building2, Crown } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export interface PlanFeature {
    text: string;
    included: boolean;
}

export interface PlanCardProps {
    id: string;
    name: string;
    description: string;
    monthlyPrice: number | null;
    annualPrice: number | null;
    cteLimit: string;
    features: PlanFeature[];
    highlighted?: boolean;
    isAnnual: boolean;
    isSelected: boolean;
    onSelect: (id: string) => void;
    appliedCredit?: number;
}

const TIER_ICONS: Record<string, React.ElementType> = {
    starter: Zap,
    growth: Rocket,
    scale: Star,
    enterprise: Crown,
};

const TIER_GRADIENTS: Record<string, string> = {
    starter: 'linear-gradient(135deg, #10b981, #059669)',
    growth: 'linear-gradient(135deg, #3b82f6, #2563eb)',
    scale: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
    enterprise: 'linear-gradient(135deg, #f59e0b, #d97706)',
};

export function PlanCard({
    id,
    name,
    description,
    monthlyPrice,
    annualPrice,
    cteLimit,
    features,
    highlighted = false,
    isAnnual,
    isSelected,
    onSelect,
    appliedCredit = 0,
}: PlanCardProps) {
    const Icon = TIER_ICONS[id] || Building2;
    const gradient = TIER_GRADIENTS[id] || TIER_GRADIENTS.starter;
    const price = isAnnual ? annualPrice : monthlyPrice;
    const isEnterprise = monthlyPrice === null;

    const savings = monthlyPrice && annualPrice ? (monthlyPrice - annualPrice) * 12 : 0;

    return (
        <motion.button
            onClick={() => onSelect(id)}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.99 }}
            className="relative flex flex-col p-6 rounded-2xl border text-left transition-all duration-300 w-full"
            style={{
                background: isSelected
                    ? 'var(--re-surface-elevated)'
                    : 'var(--re-surface-card)',
                borderColor: isSelected
                    ? 'var(--re-brand)'
                    : highlighted
                        ? 'var(--re-info)'
                        : 'var(--re-border-default)',
                boxShadow: isSelected
                    ? '0 0 24px rgba(16, 185, 129, 0.15), inset 0 1px 0 rgba(255,255,255,0.05)'
                    : highlighted
                        ? '0 0 16px rgba(59, 130, 246, 0.1)'
                        : 'var(--re-shadow-sm)',
            }}
        >
            {/* Selected indicator */}
            {isSelected && (
                <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="absolute -top-2 -right-2 w-6 h-6 rounded-full flex items-center justify-center"
                    style={{ background: 'var(--re-brand)' }}
                >
                    <Check className="w-3.5 h-3.5" style={{ color: 'var(--re-surface-base)' }} />
                </motion.div>
            )}

            {/* Popular badge */}
            {highlighted && (
                <Badge
                    className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 text-xs font-semibold"
                    style={{ background: 'var(--re-info)', color: '#fff' }}
                >
                    Most Popular
                </Badge>
            )}

            {/* Header */}
            <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-xl" style={{ background: gradient }}>
                    <Icon className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h3 className="font-bold text-lg" style={{ color: 'var(--re-text-primary)' }}>
                        {name}
                    </h3>
                    <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>
                        {description}
                    </p>
                </div>
            </div>

            {/* Price */}
            <div className="mt-2 mb-4">
                {isEnterprise ? (
                    <div>
                        <span className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>
                            Custom
                        </span>
                        <p className="text-sm mt-1" style={{ color: 'var(--re-text-muted)' }}>
                            Contact sales for pricing
                        </p>
                    </div>
                ) : (
                    <div>
                        <div className="flex items-baseline gap-1">
                            <span className="text-3xl font-extrabold" style={{ color: 'var(--re-text-primary)' }}>
                                ${price}
                            </span>
                            <span className="text-sm" style={{ color: 'var(--re-text-muted)' }}>
                                /mo
                            </span>
                        </div>
                        {isAnnual && savings > 0 && (
                            <p className="text-xs mt-1" style={{ color: 'var(--re-success)' }}>
                                Save ${savings}/year with annual billing
                            </p>
                        )}
                        {appliedCredit > 0 && (
                            <p className="text-xs mt-1 font-medium" style={{ color: 'var(--re-brand)' }}>
                                -${(appliedCredit / 100).toFixed(0)} credit applied
                            </p>
                        )}
                    </div>
                )}
            </div>

            {/* CTE limit */}
            <div
                className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg text-sm"
                style={{ background: 'var(--re-surface-base)', color: 'var(--re-text-secondary)' }}
            >
                <span className="font-mono font-semibold">{cteLimit}</span>
                <span className="text-xs" style={{ color: 'var(--re-text-muted)' }}>
                    CTEs/month
                </span>
            </div>

            {/* Features */}
            <ul className="space-y-2 flex-1">
                {features.map((feature) => (
                    <li key={feature.text} className="flex items-start gap-2 text-sm">
                        {feature.included ? (
                            <Check className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--re-success)' }} />
                        ) : (
                            <X className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--re-text-muted)' }} />
                        )}
                        <span
                            style={{
                                color: feature.included ? 'var(--re-text-secondary)' : 'var(--re-text-muted)',
                            }}
                        >
                            {feature.text}
                        </span>
                    </li>
                ))}
            </ul>
        </motion.button>
    );
}
