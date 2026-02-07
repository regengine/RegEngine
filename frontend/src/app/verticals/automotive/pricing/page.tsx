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
        id: 'starter', name: 'Starter', icon: Zap, description: 'For Tier 3 automotive suppliers', monthlyPrice: 2999, annualPrice: 2499, facilityLimit: '1-3', highlighted: false, cta: 'Start Free Trial', ctaVariant: 'outline' as const,
        features: [
            { text: 'Up to 3 facilities', included: true },
            { text: 'IATF 16949 compliance', included: true },
            { text: 'PPAP generation', included: true },
            { text: 'Quality record management', included: true },
            { text: 'Email support', included: true },
            { text: '7-year data retention', included: true },
            { text: 'Supplier portal', included: false },
            { text: 'OEM integration', included: false },
        ],
    },
    {
        id: 'professional', name: 'Professional', icon: Rocket, description: 'For Tier 2 suppliers and system integrators', monthlyPrice: 7999, annualPrice: 6665, facilityLimit: '4-15', highlighted: true, cta: 'Start Free Trial', ctaVariant: 'default' as const,
        features: [
            { text: 'Everything in Starter', included: true },
            { text: 'Up to 15 facilities', included: true },
            { text: 'VDA 6.3 & AIAG support', included: true },
            { text: 'Layered Process Audits', included: true },
            { text: 'Advanced change control', included: true },
            { text: 'Supplier portal access', included: true },
            { text: 'Priority support', included: true },
            { text: 'SSO/SAML', included: true },
        ],
    },
    {
        id: 'enterprise', name: 'Enterprise', icon: Building2, description: 'For Tier 1 and global suppliers', monthlyPrice: 19999, annualPrice: 16665, facilityLimit: '16-100', highlighted: false, cta: 'Contact Sales', ctaVariant: 'outline' as const,
        features: [
            { text: 'Everything in Professional', included: true },
            { text: 'Up to 100 facilities', included: true },
            { text: 'OEM portal integrations', included: true },
            { text: 'API access for ERP/MES', included: true },
            { text: 'White-label PPAP reports', included: true },
            { text: 'Dedicated success manager', included: true },
            { text: 'Enterprise SLA', included: true },
            { text: '24/7 support', included: true },
        ],
    },
    {
        id: 'custom', name: 'Custom', icon: Crown, description: 'For OEMs and global automotive groups', monthlyPrice: null, annualPrice: null, facilityLimit: 'Unlimited', highlighted: false, cta: 'Contact Sales', ctaVariant: 'outline' as const, href: 'mailto:sales@regengine.co?subject=Automotive%20Enterprise%20Inquiry',
        features: [
            { text: 'Unlimited facilities', included: true },
            { text: 'On-premise deployment', included: true },
            { text: 'Multi-region compliance', included: true },
            { text: 'Custom OEM integrations', included: true },
            { text: 'Executive briefings', included: true },
            { text: 'Compliance consulting', included: true },
            { text: 'Dedicated account team', included: true },
            { text: 'Incident response SLA', included: true },
        ],
    },
];

export default function AutomotivePricingPage() {
    const [annual, setAnnual] = useState(true);

    return (
        <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">            <div className="py-16 px-4">
                <div className="max-w-4xl mx-auto text-center">
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                        <Badge className="mb-4 bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300">IATF 16949 & VDA 6.3</Badge>
                        <h1 className="text-4xl md:text-5xl font-bold mb-4">Automotive Compliance,<br /><span className="text-slate-600">Zero-Defect Quality</span></h1>
                        <p className="text-xl text-muted-foreground mb-8">Automated PPAP and audit-ready quality records.</p>
                        <div className="flex items-center justify-center gap-4">
                            <button type="button" onClick={() => setAnnual(false)} className={`cursor-pointer transition-colors ${!annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>Monthly</button>
                            <Switch checked={annual} onCheckedChange={setAnnual} />
                            <button type="button" onClick={() => setAnnual(true)} className={`cursor-pointer transition-colors flex items-center ${annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>Annual<Badge variant="secondary" className="ml-2 bg-slate-100 text-slate-700">Save 17%</Badge></button>
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
                                <Card className={`h-full flex flex-col ${tier.highlighted ? 'border-slate-300 border-2' : ''}`}>
                                    {tier.highlighted && (<div className="bg-slate-600 text-white text-center py-1 text-sm font-medium">Most Popular</div>)}
                                    <CardHeader>
                                        <div className="flex items-center gap-2">
                                            <div className={`p-2 rounded-lg ${tier.highlighted ? 'bg-slate-100 dark:bg-slate-900' : 'bg-gray-100 dark:bg-gray-800'}`}>
                                                <Icon className={`h-5 w-5 ${tier.highlighted ? 'text-slate-600' : 'text-gray-600'}`} />
                                            </div>
                                            <CardTitle>{tier.name}</CardTitle>
                                        </div>
                                        <CardDescription>{tier.description}</CardDescription>
                                    </CardHeader>
                                    <CardContent className="flex-1 flex flex-col">
                                        <div className="mb-6">
                                            {price !== null ? (<div className="flex items-baseline gap-1"><span className="text-4xl font-bold">${price.toLocaleString()}</span><span className="text-muted-foreground">/mo</span></div>) : (<div className="text-2xl font-bold">Custom</div>)}
                                            <p className="text-sm text-muted-foreground mt-1">{tier.facilityLimit} facilities</p>
                                        </div>
                                        <div className="space-y-3 flex-1">
                                            {tier.features.map((feature, i) => (<div key={i} className="flex items-start gap-2">{feature.included ? <Check className="h-4 w-4 text-slate-600 mt-0.5" /> : <X className="h-4 w-4 text-gray-300 mt-0.5" />}<span className={feature.included ? '' : 'text-muted-foreground'}>{feature.text}</span></div>))}
                                        </div>
                                        <Link href={tier.id === 'custom' ? (tier as any).href || 'mailto:sales@regengine.co' : `/onboarding?plan=${tier.id}&vertical=automotive`}>
                                            <Button variant={tier.ctaVariant} className="w-full mt-6">{tier.cta}<ArrowRight className="ml-2 h-4 w-4" /></Button>
                                        </Link>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>
            </div>
            <div className="bg-gradient-to-r from-slate-600 to-gray-700 py-16 px-4">
                <div className="max-w-3xl mx-auto text-center text-white">
                    <h2 className="text-3xl font-bold mb-4">Ready for Seamless PPAP?</h2>
                    <p className="text-lg text-white/90 mb-8">14-day free trial. No credit card required.</p>
                    <Link href="/verticals/automotive"><Button size="lg" className="bg-white text-slate-700 hover:bg-white/90">Learn More About Automotive Compliance<ArrowRight className="ml-2 h-4 w-4" /></Button></Link>
                </div>
            </div>
        </div>
    );
}
