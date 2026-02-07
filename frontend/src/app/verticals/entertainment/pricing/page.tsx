'use client';

import Link from 'next/link';
import { Check, Film, ArrowRight, HelpCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function EntertainmentPricingPage() {
    const pricingTiers = [
        {
            name: 'Independent Producer',
            price: '$60K',
            period: '/year',
            description: 'For indie producers and small production companies',
            badge: null,
            features: [
                '1-5 productions per year',
                'Unlimited crew eligibility checks',
                'SAG-AFTRA & IATSE rule enforcement',
                'Single-state production tracking',
                'Mobile safety incident reporting',
                'Email support (24-hour response)',
                'SOC 2 compliant infrastructure',
                'Weekly compliance reports',
            ],
            limitations: [
                'Single production dashboard',
                'Up to 100 crew members per production',
                'Standard integration (API + CSV import)',
            ],
            cta: 'Start Free Trial',
            ctaHref: '/contact?plan=independent',
        },
        {
            name: 'Production Company',
            price: '$100K',
            period: '/year',
            description: 'For mid-size production companies',
            badge: 'Most Popular',
            features: [
                '6-15 productions per year',
                'Unlimited crew eligibility checks',
                'All union rule enforcement (SAG, IATSE, DGA, Teamsters)',
                'Multi-state production dashboard',
                'Real-time compliance alerts',
                'Mobile safety incident reporting + OSHA auto-notification',
                'Priority support (4-hour response)',
                'Dedicated onboarding specialist',
                'Entertainment Partners / Cast & Crew integration',
                'Weekly + monthly executive reports',
                'Tax credit documentation tracking',
            ],
            limitations: [
                'Up to 300 crew members per production',
                'Standard SLA',
            ],
            cta: 'Contact Sales',
            ctaHref: '/contact?plan=production-company',
        },
        {
            name: 'Studio / Network',
            price: '$150K+',
            period: '/year',
            description: 'For major studios and streaming networks',
            badge: 'Enterprise',
            features: [
                '16+ productions per year',
                'Unlimited crew eligibility checks',
                'All union rule enforcement + custom CBAs',
                'Multi-production unified dashboard (20+ simultaneous shoots)',
                'Real-time compliance alerts + SMS/Slack integration',
                'Mobile safety incident reporting + OSHA auto-notification',
                'White-glove support (1-hour response, dedicated Slack channel)',
                'Dedicated customer success manager',
                'Full API access + custom integrations',
                'Daily executive dashboards',
                'Tax credit + incentive tracking (CA, NY, GA, NM, LA, BC)',
                'Third-party timestamp anchoring (RFC 3161)',
                'Custom SLA (priority response)',
                'Annual on-site compliance audit',
            ],
            limitations: [],
            cta: 'Contact Sales',
            ctaHref: '/contact?plan=studio',
        },
    ];

    const addons = [
        {
            name: 'Third-Party Timestamp Anchoring',
            description: 'Cryptographic timestamps from VeriSign/DigiCert for legally defensible audit trails',
            price: '$5K/year',
        },
        {
            name: 'Additional State Labor Law Module',
            description: 'Add support for additional states beyond CA, NY, GA (e.g., NM, LA, BC)',
            price: '$2K/state/year',
        },
        {
            name: 'Custom Union CBA Integration',
            description: 'Custom rule enforcement for non-standard union agreements',
            price: '$10K one-time + $2K/year',
        },
        {
            name: 'On-Site Training Workshop',
            description: 'Full-day training for UPMs, 1st ADs, and production coordinators',
            price: '$5K per session',
        },
    ];

    const faqs = [
        {
            q: 'What happens if we exceed our production limit?',
            a: 'You can upgrade to the next tier mid-contract or pay overage fees ($8K per production for Independent, $5K for Production Company). We recommend choosing a tier with 20% headroom above your typical volume.',
        },
        {
            q: 'Do you integrate with Entertainment Partners or Cast & Crew?',
            a: 'Yes. PCOS integrates via API with both Entertainment Partners and Cast & Crew payroll systems. PCOS handles real-time compliance enforcement, EP/C&C handle payroll processing.',
        },
        {
            q: 'What if PCOS goes down during a shoot?',
            a: 'PCOS is built on enterprise-grade infrastructure with proactive monitoring. In the unlikely event of downtime, you can export call sheets to PDF for distribution. The system is asynchronous—downtime doesn\'t block production, it just temporarily removes real-time validation.',
        },
        {
            q: 'How long does implementation take?',
            a: '90 days from contract signature to full rollout: 30 days configuration, 30 days pilot production, 30 days full rollout. You can start using PCOS on pilot productions within 30 days.',
        },
        {
            q: 'What unions do you support?',
            a: 'SAG-AFTRA, IATSE, DGA, and Teamsters are standard. We can add custom union CBAs (e.g., regional IATSE locals, specialty guilds) via the Custom Union CBA Integration add-on.',
        },
        {
            q: 'Is there a free trial?',
            a: 'Yes, we offer a 30-day pilot production trial for qualified production companies. You can test PCOS on one production before committing to an annual contract.',
        },
    ];

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            {/* Hero */}
            <section className="pt-20 pb-12 px-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
                <div className="max-w-6xl mx-auto text-center">
                    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/20 mb-6">
                        <Film className="h-5 w-5" />
                        <span className="text-sm font-medium">PCOS Pricing</span>
                    </div>

                    <h1 className="text-4xl md:text-5xl font-bold mb-4">
                        Transparent, Production-Based Pricing
                    </h1>
                    <p className="text-xl text-purple-100 max-w-3xl mx-auto mb-8">
                        Choose a tier based on your annual production volume. All plans include unlimited crew checks and union rule enforcement.
                    </p>

                    <div className="flex justify-center gap-4">
                        <Link href="/verticals/entertainment/calculator">
                            <Button size="lg" variant="secondary">
                                Calculate Your ROI
                            </Button>
                        </Link>
                        <Link href="/pcos">
                            <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                Try Demo
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>

            {/* Pricing Tiers */}
            <section className="py-16 px-4">
                <div className="max-w-7xl mx-auto">
                    <div className="grid md:grid-cols-3 gap-8">
                        {pricingTiers.map((tier, index) => (
                            <Card
                                key={tier.name}
                                className={`relative ${index === 1 ? 'border-2 border-purple-600 shadow-xl' : ''}`}
                            >
                                {tier.badge && (
                                    <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                                        <Badge className="bg-purple-600 text-white px-4 py-1">
                                            {tier.badge}
                                        </Badge>
                                    </div>
                                )}

                                <CardHeader className={index === 1 ? 'pt-8' : ''}>
                                    <CardTitle className="text-2xl">{tier.name}</CardTitle>
                                    <CardDescription>{tier.description}</CardDescription>
                                    <div className="mt-4">
                                        <span className="text-4xl font-bold">{tier.price}</span>
                                        <span className="text-muted-foreground">{tier.period}</span>
                                    </div>
                                </CardHeader>

                                <CardContent>
                                    <div className="space-y-4">
                                        <div>
                                            <h4 className="font-semibold mb-3">What's included:</h4>
                                            <ul className="space-y-2">
                                                {tier.features.map((feature) => (
                                                    <li key={feature} className="flex items-start gap-2 text-sm">
                                                        <Check className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
                                                        <span>{feature}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>

                                        {tier.limitations.length > 0 && (
                                            <div className="pt-4 border-t">
                                                <ul className="space-y-2">
                                                    {tier.limitations.map((limitation) => (
                                                        <li key={limitation} className="flex items-start gap-2 text-sm text-muted-foreground">
                                                            <span className="text-xs mt-0.5">•</span>
                                                            <span>{limitation}</span>
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}

                                        <Link href={tier.ctaHref}>
                                            <Button
                                                className="w-full mt-4"
                                                variant={index === 1 ? 'default' : 'outline'}
                                            >
                                                {tier.cta}
                                                <ArrowRight className="ml-2 h-4 w-4" />
                                            </Button>
                                        </Link>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </div>
            </section>

            {/* Add-Ons */}
            <section className="py-16 px-4 bg-muted/30">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl font-bold mb-4">Optional Add-Ons</h2>
                        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                            Extend PCOS with additional modules and services
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 gap-6">
                        {addons.map((addon) => (
                            <Card key={addon.name}>
                                <CardHeader>
                                    <div className="flex justify-between items-start">
                                        <div>
                                            <CardTitle className="text-lg">{addon.name}</CardTitle>
                                            <CardDescription className="mt-2">{addon.description}</CardDescription>
                                        </div>
                                        <Badge variant="outline" className="ml-4 flex-shrink-0">
                                            {addon.price}
                                        </Badge>
                                    </div>
                                </CardHeader>
                            </Card>
                        ))}
                    </div>
                </div>
            </section>

            {/* Comparison Table */}
            <section className="py-16 px-4">
                <div className="max-w-6xl mx-auto">
                    <h2 className="text-3xl font-bold mb-8 text-center">Feature Comparison</h2>

                    <div className="overflow-x-auto">
                        <table className="w-full border-collapse">
                            <thead>
                                <tr className="border-b">
                                    <th className="text-left p-4 font-semibold">Feature</th>
                                    <th className="text-center p-4 font-semibold">Independent</th>
                                    <th className="text-center p-4 font-semibold bg-purple-50 dark:bg-purple-900/20">Production Co</th>
                                    <th className="text-center p-4 font-semibold">Studio</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr className="border-b">
                                    <td className="p-4">Productions per year</td>
                                    <td className="text-center p-4">1-5</td>
                                    <td className="text-center p-4 bg-purple-50 dark:bg-purple-900/20">6-15</td>
                                    <td className="text-center p-4">16+</td>
                                </tr>
                                <tr className="border-b">
                                    <td className="p-4">Union rule enforcement</td>
                                    <td className="text-center p-4"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                    <td className="text-center p-4 bg-purple-50 dark:bg-purple-900/20"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                    <td className="text-center p-4"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                </tr>
                                <tr className="border-b">
                                    <td className="p-4">Multi-state tracking</td>
                                    <td className="text-center p-4">Single state</td>
                                    <td className="text-center p-4 bg-purple-50 dark:bg-purple-900/20"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                    <td className="text-center p-4"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                </tr>
                                <tr className="border-b">
                                    <td className="p-4">Support response time</td>
                                    <td className="text-center p-4">24 hours</td>
                                    <td className="text-center p-4 bg-purple-50 dark:bg-purple-900/20">4 hours</td>
                                    <td className="text-center p-4">1 hour</td>
                                </tr>
                                <tr className="border-b">
                                    <td className="p-4">Tax credit tracking</td>
                                    <td className="text-center p-4">—</td>
                                    <td className="text-center p-4 bg-purple-50 dark:bg-purple-900/20"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                    <td className="text-center p-4"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                </tr>
                                <tr className="border-b">
                                    <td className="p-4">Custom integrations</td>
                                    <td className="text-center p-4">—</td>
                                    <td className="text-center p-4 bg-purple-50 dark:bg-purple-900/20">Standard API</td>
                                    <td className="text-center p-4">Full API + Custom</td>
                                </tr>
                                <tr className="border-b">
                                    <td className="p-4">Timestamp anchoring</td>
                                    <td className="text-center p-4">Add-on</td>
                                    <td className="text-center p-4 bg-purple-50 dark:bg-purple-900/20">Add-on</td>
                                    <td className="text-center p-4"><Check className="h-5 w-5 text-green-600 mx-auto" /></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            {/* FAQs */}
            <section className="py-16 px-4 bg-muted/30">
                <div className="max-w-4xl mx-auto">
                    <h2 className="text-3xl font-bold mb-12 text-center">Frequently Asked Questions</h2>

                    <div className="space-y-6">
                        {faqs.map((faq) => (
                            <Card key={faq.q}>
                                <CardHeader>
                                    <CardTitle className="text-lg flex items-start gap-2">
                                        <HelpCircle className="h-5 w-5 text-purple-600 mt-1 flex-shrink-0" />
                                        {faq.q}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-muted-foreground">{faq.a}</p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="py-16 px-4">
                <div className="max-w-4xl mx-auto">
                    <Card className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0">
                        <CardContent className="pt-6">
                            <div className="text-center space-y-4">
                                <h2 className="text-3xl font-bold">Still Have Questions?</h2>
                                <p className="text-purple-100 max-w-2xl mx-auto">
                                    Schedule a personalized demo or speak with our entertainment compliance team
                                </p>
                                <div className="flex justify-center gap-4 pt-4">
                                    <Link href="/contact">
                                        <Button size="lg" variant="secondary">
                                            Contact Sales
                                        </Button>
                                    </Link>
                                    <Link href="/pcos">
                                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                            Try PCOS Demo
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </section>        </div>
    );
}
