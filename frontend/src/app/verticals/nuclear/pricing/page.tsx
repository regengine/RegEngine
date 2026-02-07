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
        name: 'Tier 1',
        icon: Zap,
        description: 'For research reactors and small facilities',
        monthlyPrice: 9999,
        annualPrice: 8332,
        facilityLimit: '1-2',
        highlighted: false,
        cta: 'Contact Sales',
        ctaVariant: 'outline' as const,
        features: [
            { text: 'Up to 2 facilities', included: true },
            { text: 'Immutable evidence vault', included: true },
            { text: 'Chain-of-custody tracking', included: true },
            { text: '10 CFR compliance templates', included: true },
            { text: 'Audit-ready reports', included: true },
            { text: 'Email support', included: true },
            { text: 'Multi-site management', included: false },
            { text: 'NRC liaison support', included: false },
        ],
    },
    {
        id: 'professional',
        name: 'Tier 2',
        icon: Rocket,
        description: 'For commercial power reactors',
        monthlyPrice: 29999,
        annualPrice: 24999,
        facilityLimit: '3-5',
        highlighted: true,
        cta: 'Contact Sales',
        ctaVariant: 'default' as const,
        features: [
            { text: 'Everything in Tier 1', included: true },
            { text: 'Up to 5 facilities', included: true },
            { text: 'Automated change detection', included: true },
            { text: 'Safety culture tracking', included: true },
            { text: 'Corrective action programs', included: true },
            { text: 'Dedicated compliance manager', included: true },
            { text: 'Priority support', included: true },
            { text: 'SSO/SAML', included: true },
        ],
    },
    {
        id: 'enterprise',
        name: 'Tier 3',
        icon: Building2,
        description: 'For multi-site nuclear operators',
        monthlyPrice: 79999,
        annualPrice: 66665,
        facilityLimit: '6-20',
        highlighted: false,
        cta: 'Contact Sales',
        ctaVariant: 'outline' as const,
        features: [
            { text: 'Everything in Tier 2', included: true },
            { text: 'Up to 20 facilities', included: true },
            { text: 'White-label NRC reports', included: true },
            { text: 'API access for SCADA integration', included: true },
            { text: 'Dedicated success manager', included: true },
            { text: 'Compliance consulting hours', included: true },
            { text: '99.99% SLA', included: true },
            { text: '24/7 emergency support', included: true },
        ],
    },
    {
        id: 'custom',
        name: 'Custom',
        icon: Crown,
        description: 'For fleet operators and DOE facilities',
        monthlyPrice: null,
        annualPrice: null,
        facilityLimit: '20+',
        highlighted: false,
        cta: 'Contact Sales',
        ctaVariant: 'outline' as const,
        href: 'mailto:sales@regengine.co?subject=Nuclear%20Enterprise%20Inquiry',
        features: [
            { text: 'Unlimited facilities', included: true },
            { text: 'On-premise deployment', included: true },
            { text: 'Custom contract terms', included: true },
            { text: 'NRC liaison support', included: true },
            { text: 'Executive briefings', included: true },
            { text: 'SOC 2 Type II certified', included: true },
            { text: 'Security clearance support', included: true },
            { text: 'Disaster recovery SLA', included: true },
        ],
    },
];

export default function NuclearPricingPage() {
    const [annual, setAnnual] = useState(true);

    return (
        <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
            <div className="py-16 px-4">
                <div className="max-w-4xl mx-auto text-center">
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                        <Badge className="mb-4 bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300">NRC 10 CFR Compliance</Badge>
                        <h1 className="text-4xl md:text-5xl font-bold mb-4">
                            Nuclear Regulatory Compliance,<br />
                            <span className="text-red-600">Safety-Critical Infrastructure</span>
                        </h1>
                        <p className="text-xl text-muted-foreground mb-8">
                            Immutable evidence layer for NRC inspections and audits.
                        </p>

                        <div className="flex items-center justify-center gap-4">
                            <button type="button" onClick={() => setAnnual(false)} className={`cursor-pointer transition-colors ${!annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                                Monthly
                            </button>
                            <Switch checked={annual} onCheckedChange={setAnnual} />
                            <button type="button" onClick={() => setAnnual(true)} className={`cursor-pointer transition-colors flex items-center ${annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                                Annual
                                <Badge variant="secondary" className="ml-2 bg-red-100 text-red-700">Save 17%</Badge>
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
                                <Card className={`h-full flex flex-col ${tier.highlighted ? 'border-red-300 border-2' : ''}`}>
                                    {tier.highlighted && (<div className="bg-red-600 text-white text-center py-1 text-sm font-medium">Most Popular</div>)}
                                    <CardHeader>
                                        <div className="flex items-center gap-2">
                                            <div className={`p-2 rounded-lg ${tier.highlighted ? 'bg-red-100 dark:bg-red-900' : 'bg-gray-100 dark:bg-gray-800'}`}>
                                                <Icon className={`h-5 w-5 ${tier.highlighted ? 'text-red-600' : 'text-gray-600'}`} />
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
                                            <p className="text-sm text-muted-foreground mt-1">{tier.facilityLimit} facilities</p>
                                        </div>
                                        <div className="space-y-3 flex-1">
                                            {tier.features.map((feature, i) => (
                                                <div key={i} className="flex items-start gap-2">
                                                    {feature.included ? <Check className="h-4 w-4 text-red-600 mt-0.5" /> : <X className="h-4 w-4 text-gray-300 mt-0.5" />}
                                                    <span className={feature.included ? '' : 'text-muted-foreground'}>{feature.text}</span>
                                                </div>
                                            ))}
                                        </div>
                                        <Link href={tier.id === 'custom' ? (tier as any).href || 'mailto:sales@regengine.co' : `mailto:sales@regengine.co?subject=${tier.name}%20Inquiry&body=I'm%20interested%20in%20the%20${tier.name}%20plan%20for%20nuclear%20compliance.`}>
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

            <div className="bg-gradient-to-r from-red-600 to-orange-600 py-16 px-4">
                <div className="max-w-3xl mx-auto text-center text-white">
                    <h2 className="text-3xl font-bold mb-4">Ready for Your NRC Inspection?</h2>
                    <p className="text-lg text-white/90 mb-8">Contact us for a personalized demo and compliance assessment.</p>
                    <Link href="/verticals/nuclear">
                        <Button size="lg" className="bg-white text-red-700 hover:bg-white/90">
                            Learn More About Nuclear Compliance
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    </Link>
                </div>
            </div>
        </div>
    );
}
