'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Check, X, Zap, Building2, Rocket, Crown, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import Link from 'next/link';

const PRICING_TIERS = [
    {
        id: 'starter',
        name: 'Starter',
        icon: Zap,
        description: 'For small practices and clinics',
        monthlyPrice: 899,
        annualPrice: 749,
        patientLimit: '1K',
        highlighted: false,
        cta: 'Start Free Trial',
        ctaVariant: 'outline' as const,
        features: [
            { text: 'Up to 1K patient records', included: true },
            { text: 'HIPAA compliance tracking', included: true },
            { text: 'Audit trail generation', included: true },
            { text: 'Breach documentation', included: true },
            { text: 'Email support', included: true },
            { text: '6-year data retention', included: true },
            { text: 'Multi-location support', included: false },
            { text: 'BAA included', included: false },
        ],
    },
    {
        id: 'professional',
        name: 'Professional',
        icon: Rocket,
        description: 'For hospitals and health systems',
        monthlyPrice: 2999,
        annualPrice: 2499,
        patientLimit: '50K',
        highlighted: true,
        cta: 'Start Free Trial',
        ctaVariant: 'default' as const,
        features: [
            { text: 'Everything in Starter', included: true },
            { text: 'Up to 50K patient records', included: true },
            { text: 'PHI access logging', included: true },
            { text: 'Incident response workflows', included: true },
            { text: 'Custom attestation templates', included: true },
            { text: 'Unlimited data retention', included: true },
            { text: 'Priority support', included: true },
            { text: 'BAA included', included: true },
        ],
    },
    {
        id: 'enterprise',
        name: 'Enterprise',
        icon: Building2,
        description: 'For integrated delivery networks',
        monthlyPrice: 9999,
        annualPrice: 8332,
        patientLimit: '500K',
        highlighted: false,
        cta: 'Contact Sales',
        ctaVariant: 'outline' as const,
        features: [
            { text: 'Everything in Professional', included: true },
            { text: 'Up to 500K patient records', included: true },
            { text: 'EHR integration support', included: true },
            { text: 'API access', included: true },
            { text: 'Dedicated success manager', included: true },
            { text: 'Multi-location management', included: true },
            { text: 'Enterprise SLA', included: true },
            { text: '24/7 support', included: true },
        ],
    },
    {
        id: 'custom',
        name: 'Custom',
        icon: Crown,
        description: 'For national health networks',
        monthlyPrice: null,
        annualPrice: null,
        patientLimit: 'Unlimited',
        highlighted: false,
        cta: 'Contact Sales',
        ctaVariant: 'outline' as const,
        href: 'mailto:sales@regengine.co?subject=Healthcare%20Enterprise%20Inquiry',
        features: [
            { text: 'Unlimited patient records', included: true },
            { text: 'On-premise deployment', included: true },
            { text: 'Custom contract terms', included: true },
            { text: 'Compliance consulting', included: true },
            { text: 'Custom integrations', included: true },
            { text: 'HITRUST certified', included: true },
            { text: 'Executive briefings', included: true },
            { text: 'Incident response SLA', included: true },
        ],
    },
];

export default function HealthcarePricingPage() {
    const [annual, setAnnual] = useState(true);

    return (
        <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
            <div className="py-16 px-4">
                <div className="max-w-4xl mx-auto text-center">
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                        <Badge className="mb-4 bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300">HIPAA Compliance</Badge>
                        <h1 className="text-4xl md:text-5xl font-bold mb-4">
                            Healthcare Compliance,<br />
                            <span className="text-purple-600">Patient Privacy Protected</span>
                        </h1>
                        <p className="text-xl text-muted-foreground mb-8">
                            Immutable PHI access logs and HIPAA audit trails.
                        </p>

                        <div className="flex items-center justify-center gap-4">
                            <button type="button" onClick={() => setAnnual(false)} className={`cursor-pointer transition-colors ${!annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>Monthly</button>
                            <Switch checked={annual} onCheckedChange={setAnnual} />
                            <button type="button" onClick={() => setAnnual(true)} className={`cursor-pointer transition-colors flex items-center ${annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                                Annual
                                <Badge variant="secondary" className="ml-2 bg-purple-100 text-purple-700">Save 17%</Badge>
                            </button>
                        </div>
                    </motion.div>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 pb-16">
                <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {PRICING_TIERS.map((tier, index) => {
                        const Icon = tier.icon;
                        const price = annual ? tier.annualPrice : tier.monthlyPrice;
                        return (
                            <motion.div key={tier.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.1 }}>
                                <Card className={`h-full flex flex-col ${tier.highlighted ? 'border-purple-300 border-2' : ''}`}>
                                    {tier.highlighted && (<div className="bg-purple-600 text-white text-center py-1 text-sm font-medium">Most Popular</div>)}
                                    <CardHeader>
                                        <div className="flex items-center gap-2">
                                            <div className={`p-2 rounded-lg ${tier.highlighted ? 'bg-purple-100 dark:bg-purple-900' : 'bg-gray-100 dark:bg-gray-800'}`}>
                                                <Icon className={`h-5 w-5 ${tier.highlighted ? 'text-purple-600' : 'text-gray-600'}`} />
                                            </div>
                                            <CardTitle>{tier.name}</CardTitle>
                                        </div>
                                        <CardDescription>{tier.description}</CardDescription>
                                    </CardHeader>
                                    <CardContent className="flex-1 flex flex-col">
                                        <div className="mb-6">
                                            {price !== null ? (
                                                <div className="flex items-baseline gap-1">
                                                    <span className="text-4xl font-bold">${price.toLocaleString()}</span>
                                                    <span className="text-muted-foreground">/mo</span>
                                                </div>
                                            ) : (
                                                <div className="text-2xl font-bold">Custom</div>
                                            )}
                                            <p className="text-sm text-muted-foreground mt-1">{tier.patientLimit} patients</p>
                                        </div>
                                        <div className="space-y-3 flex-1">
                                            {tier.features.map((feature, i) => (
                                                <div key={i} className="flex items-start gap-2">
                                                    {feature.included ? <Check className="h-4 w-4 text-purple-600 mt-0.5" /> : <X className="h-4 w-4 text-gray-300 mt-0.5" />}
                                                    <span className={feature.included ? '' : 'text-muted-foreground'}>{feature.text}</span>
                                                </div>
                                            ))}
                                        </div>
                                        <Link href={tier.id === 'custom' ? (tier as any).href || 'mailto:sales@regengine.co' : `/onboarding?plan=${tier.id}&vertical=healthcare`}>
                                            <Button variant={tier.ctaVariant} className="w-full mt-6">
                                                {tier.cta}
                                                <ArrowRight className="ml-2 h-4 w-4" />
                                            </Button>
                                        </Link>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>
            </div>

            <div className="bg-gradient-to-r from-purple-600 to-pink-600 py-16 px-4">
                <div className="max-w-3xl mx-auto text-center text-white">
                    <h2 className="text-3xl font-bold mb-4">Ready to Simplify HIPAA Compliance?</h2>
                    <p className="text-lg text-white/90 mb-8">14-day free trial. BAA available. No credit card required.</p>
                    <Link href="/verticals/healthcare">
                        <Button size="lg" className="bg-white text-purple-700 hover:bg-white/90">
                            Learn More About Healthcare Compliance
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    </Link>
                </div>
            </div>
        </div>
    );
}
