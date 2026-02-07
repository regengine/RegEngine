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
        id: 'starter', name: 'Starter', icon: Zap, description: 'For small contractors and builders', monthlyPrice: 999, annualPrice: 832, projectLimit: '1-10', cta: 'Start Free Trial', ctaVariant: 'outline' as const,
        features: [
            { text: 'Up to 10 active projects', included: true },
            { text: 'ISO 19650 (BIM) compliance', included: true },
            { text: 'Safety record tracking', included: true },
            { text: 'Change order documentation', included: true },
            { text: 'Email support', included: true },
            { text: '7-year data retention', included: true },
            { text: 'Multi-site management', included: false },
            { text: 'OSHA compliance tracking', included: false },
        ],
    },
    {
        id: 'professional', name: 'Professional', icon: Rocket, description: 'For general contractors', monthlyPrice: 3999, annualPrice: 3332, projectLimit: '11-50', highlighted: true, cta: 'Start Free Trial', ctaVariant: 'default' as const,
        features: [
            { text: 'Everything in Starter', included: true },
            { text: 'Up to 50 active projects', included: true },
            { text: 'OSHA 1926 compliance', included: true },
            { text: 'Safety incident reporting', included: true },
            { text: 'RFI & submittal tracking', included: true },
            { text: 'Subcontractor qualification', included: true },
            { text: 'Priority support', included: true },
            { text: 'SSO/SAML', included: true },
        ],
    },
    {
        id: 'enterprise', name: 'Enterprise', icon: Building2, description: 'For commercial builders', monthlyPrice: 9999, annualPrice: 8332, projectLimit: '51-200', cta: 'Contact Sales', ctaVariant: 'outline' as const,
        features: [
            { text: 'Everything in Professional', included: true },
            { text: 'Up to 200 active projects', included: true },
            { text: 'API access for project management software', included: true },
            { text: 'Custom compliance checklists', included: true },
            { text: 'Dedicated success manager', included: true },
            { text: 'Unlimited data retention', included: true },
            { text: 'Enterprise SLA', included: true },
            { text: '24/7 support', included: true },
        ],
    },
    {
        id: 'custom', name: 'Custom', icon: Crown, description: 'For national construction firms', monthlyPrice: null, annualPrice: null, projectLimit: 'Unlimited', cta: 'Contact Sales', ctaVariant: 'outline' as const, href: 'mailto:sales@regengine.co?subject=Construction%20Enterprise%20Inquiry',
        features: [
            { text: 'Unlimited projects', included: true },
            { text: 'On-premise deployment', included: true },
            { text: 'Multi-region compliance', included: true },
            { text: 'Custom integrations', included: true },
            { text: 'Audit-ready reporting', included: true },
            { text: 'Executive briefings', included: true },
            { text: 'Dedicated account team', included: true },
            { text: 'Incident response SLA', included: true },
        ],
    },
];

export default function ConstructionPricingPage() {
    const [annual, setAnnual] = useState(true);
    return (
        <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">            <div className="py-16 px-4"><div className="max-w-4xl mx-auto text-center"><motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}><Badge className="mb-4 bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300">ISO 19650 & OSHA 1926</Badge><h1 className="text-4xl md:text-5xl font-bold mb-4">Construction Compliance,<br /><span className="text-amber-600">Built on Safety</span></h1><p className="text-xl text-muted-foreground mb-8">Immutable safety records and project documentation.</p><div className="flex items-center justify-center gap-4"><button type="button" onClick={() => setAnnual(false)} className={`cursor-pointer transition-colors ${!annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>Monthly</button><Switch checked={annual} onCheckedChange={setAnnual} /><button type="button" onClick={() => setAnnual(true)} className={`cursor-pointer transition-colors flex items-center ${annual ? 'font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>Annual<Badge variant="secondary" className="ml-2 bg-amber-100 text-amber-700">Save 17%</Badge></button></div></motion.div></div></div>
            <div className="max-w-7xl mx-auto px-4 pb-16"><div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">{PRICING_TIERS.map((tier, index) => { const Icon = tier.icon; const price = annual ? tier.annualPrice : tier.monthlyPrice; return (<motion.div key={tier.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.1 }}><Card className={`h-full flex flex-col ${tier.highlighted ? 'border-amber-300 border-2' : ''}`}>{tier.highlighted && (<div className="bg-amber-600 text-white text-center py-1 text-sm font-medium">Most Popular</div>)}<CardHeader><div className="flex items-center gap-2"><div className={`p-2 rounded-lg ${tier.highlighted ? 'bg-amber-100 dark:bg-amber-900' : 'bg-gray-100 dark:bg-gray-800'}`}><Icon className={`h-5 w-5 ${tier.highlighted ? 'text-amber-600' : 'text-gray-600'}`} /></div><CardTitle>{tier.name}</CardTitle></div><CardDescription>{tier.description}</CardDescription></CardHeader><CardContent className="flex-1 flex flex-col"><div className="mb-6">{price !== null ? (<div className="flex items-baseline gap-1"><span className="text-4xl font-bold">${price.toLocaleString()}</span><span className="text-muted-foreground">/mo</span></div>) : (<div className="text-2xl font-bold">Custom</div>)}<p className="text-sm text-muted-foreground mt-1">{tier.projectLimit} projects</p></div><div className="space-y-3 flex-1">{tier.features.map((feature, i) => (<div key={i} className="flex items-start gap-2">{feature.included ? <Check className="h-4 w-4 text-amber-600 mt-0.5" /> : <X className="h-4 w-4 text-gray-300 mt-0.5" />}<span className={feature.included ? '' : 'text-muted-foreground'}>{feature.text}</span></div>))}</div><Link href={tier.id === 'custom' ? (tier as any).href || 'mailto:sales@regengine.co' : `/onboarding?plan=${tier.id}&vertical=construction`}><Button variant={tier.ctaVariant} className="w-full mt-6">{tier.cta}<ArrowRight className="ml-2 h-4 w-4" /></Button></Link></CardContent></Card></motion.div>); })}</div></div>
            <div className="bg-gradient-to-r from-amber-600 to-orange-600 py-16 px-4"><div className="max-w-3xl mx-auto text-center text-white"><h2 className="text-3xl font-bold mb-4">Ready for Audit-Ready Projects?</h2><p className="text-lg text-white/90 mb-8">14-day free trial. No credit card required.</p><Link href="/verticals/construction"><Button size="lg" className="bg-white text-amber-700 hover:bg-white/90">Learn More<ArrowRight className="ml-2 h-4 w-4" /></Button></Link></div></div>
        </div>
    );
}
