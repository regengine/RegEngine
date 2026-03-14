'use client';

import { motion } from 'framer-motion';
import {
    Building2,
    Users,
    TrendingUp,
    Shield,
    CheckCircle2,
    ArrowRight,
    Mail,
    FileText,
    Handshake,
    DollarSign,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';

const PARTNER_BENEFITS = [
    {
        icon: Building2,
        title: 'White-Label Platform',
        description: 'Your branding, our technology. Multi-tenant dashboard to manage all your clients from one place.',
    },
    {
        icon: TrendingUp,
        title: 'Recurring Revenue',
        description: 'Wholesale pricing lets you keep 40-60% margin. Build predictable monthly income from compliance clients.',
    },
    {
        icon: Users,
        title: 'Scale Without Limits',
        description: 'No headcount needed. Onboard unlimited clients with the same effort as one. API does the heavy lifting.',
    },
    {
        icon: Shield,
        title: 'Competitive Edge',
        description: 'Differentiate from spreadsheet-based competitors. Offer real-time traceability, not just templates.',
    },
];

const PARTNER_TIERS = [
    {
        name: 'Referral Partner',
        description: 'Earn commission for client referrals',
        features: [
            '20% commission on first year revenue',
            'Co-branded landing pages',
            'Sales enablement materials',
            'Quarterly partner calls',
        ],
        cta: 'Join Referral Program',
    },
    {
        name: 'Implementation Partner',
        description: 'Resell and implement for clients',
        features: [
            'Wholesale pricing (40-50% off retail)',
            'White-label option available',
            'Partner certification training',
            'Dedicated partner success manager',
            'Priority support channel',
        ],
        cta: 'Apply for Partnership',
        highlighted: true,
    },
    {
        name: 'Enterprise Partner',
        description: 'Custom solutions for large deployments',
        features: [
            'Custom wholesale pricing',
            'Full white-label platform',
            'API for custom integrations',
            'Joint go-to-market activities',
            'Revenue share on renewals',
        ],
        cta: 'Contact Us',
    },
];

const TARGET_PARTNERS = [
    'SQF Consultants',
    'FDA Compliance Consultants',
    'Food Safety Certification Bodies',
    'GRC Advisory Firms',
    'Quality Management Consultants',
    'Supply Chain Consultants',
];

export default function PartnersPage() {
    return (
        <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-800">            {/* Hero Section */}
            <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white py-16">
                <div className="max-w-4xl mx-auto px-4 text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                    >
                        <Badge className="mb-4 bg-white/20 text-white hover:bg-white/30">
                            Partner Program
                        </Badge>
                        <h1 className="text-4xl md:text-5xl font-bold mb-4">
                            Scale Your FSMA 204 Practice<br />
                            <span className="text-blue-200">Without Scaling Headcount</span>
                        </h1>
                        <p className="text-xl text-white/90 mb-8 max-w-2xl mx-auto">
                            White-label RegEngine to serve unlimited food safety clients.
                            You keep the relationship, we handle the technology.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4 justify-center">
                            <Link href="mailto:partners@regengine.co?subject=Partner%20Program%20Inquiry">
                                <Button size="lg" className="bg-white text-blue-700 hover:bg-white/90">
                                    Become a Partner
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Button>
                            </Link>
                            <Link href="/demo/mock-recall">
                                <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                    See Platform Demo
                                </Button>
                            </Link>
                        </div>
                    </motion.div>
                </div>
            </div>

            {/* Why Partner */}
            <div className="max-w-6xl mx-auto px-4 py-16">
                <div className="text-center mb-12">
                    <h2 className="text-3xl font-bold mb-4">Why Partner with RegEngine?</h2>
                    <p className="text-muted-foreground max-w-2xl mx-auto">
                        One consultant with RegEngine can serve 50+ clients. Without us, you'd need
                        a team of 10. That's the power of API-first compliance.
                    </p>
                </div>

                <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {PARTNER_BENEFITS.map((benefit, index) => {
                        const Icon = benefit.icon;
                        return (
                            <motion.div
                                key={benefit.title}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: index * 0.1 }}
                            >
                                <Card className="h-full text-center">
                                    <CardHeader>
                                        <div className="mx-auto p-3 bg-blue-100 dark:bg-blue-900 rounded-lg w-fit mb-2">
                                            <Icon className="h-6 w-6 text-blue-600" />
                                        </div>
                                        <CardTitle className="text-lg">{benefit.title}</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <p className="text-sm text-muted-foreground">{benefit.description}</p>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>
            </div>

            {/* Partner Tiers */}
            <div className="bg-gray-50 dark:bg-gray-900 py-16 px-4">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl font-bold mb-4">Partnership Tiers</h2>
                        <p className="text-muted-foreground">
                            Choose the partnership level that fits your practice
                        </p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-6">
                        {PARTNER_TIERS.map((tier, index) => (
                            <motion.div
                                key={tier.name}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: index * 0.1 }}
                            >
                                <Card className={`h-full flex flex-col ${tier.highlighted
                                    ? 'border-blue-500 border-2 shadow-lg shadow-blue-100 dark:shadow-blue-900/20'
                                    : ''
                                    }`}>
                                    {tier.highlighted && (
                                        <div className="bg-blue-500 text-white text-center py-1 text-sm font-medium">
                                            Most Popular
                                        </div>
                                    )}
                                    <CardHeader>
                                        <CardTitle>{tier.name}</CardTitle>
                                        <CardDescription>{tier.description}</CardDescription>
                                    </CardHeader>
                                    <CardContent className="flex-1 flex flex-col">
                                        <ul className="space-y-3 flex-1">
                                            {tier.features.map((feature, i) => (
                                                <li key={i} className="flex items-start gap-2">
                                                    <CheckCircle2 className="h-4 w-4 text-blue-600 mt-0.5 flex-shrink-0" />
                                                    <span className="text-sm">{feature}</span>
                                                </li>
                                            ))}
                                        </ul>
                                        <Link href="mailto:partners@regengine.co?subject=Partner%20Program%20-%20" className="mt-6">
                                            <Button
                                                className={`w-full ${tier.highlighted ? 'bg-blue-600 hover:bg-blue-700' : ''}`}
                                                variant={tier.highlighted ? 'default' : 'outline'}
                                            >
                                                {tier.cta}
                                            </Button>
                                        </Link>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Partner Economics */}
            <div className="max-w-6xl mx-auto px-4 py-16">
                <Card className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border-green-200">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <DollarSign className="h-6 w-6 text-green-600" />
                            Partner Economics
                        </CardTitle>
                        <CardDescription>
                            Build recurring revenue with every client you onboard
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="grid md:grid-cols-3 gap-6">
                            <div className="text-center p-4 bg-white dark:bg-gray-800 rounded-lg">
                                <p className="text-3xl font-bold text-green-600">$650-750</p>
                                <p className="text-sm text-muted-foreground">Your wholesale cost per client/mo</p>
                            </div>
                            <div className="text-center p-4 bg-white dark:bg-gray-800 rounded-lg">
                                <p className="text-3xl font-bold text-blue-600">$1,299-2,499</p>
                                <p className="text-sm text-muted-foreground">Suggested retail price</p>
                            </div>
                            <div className="text-center p-4 bg-white dark:bg-gray-800 rounded-lg">
                                <p className="text-3xl font-bold text-purple-600">40-60%</p>
                                <p className="text-sm text-muted-foreground">Your margin per client</p>
                            </div>
                        </div>
                        <div className="mt-6 p-4 bg-white dark:bg-gray-800 rounded-lg">
                            <p className="text-center text-lg">
                                <strong>Example:</strong> 15 clients × $650 margin = <span className="text-green-600 font-bold">$9,750/month MRR</span>
                                <span className="text-muted-foreground ml-2">($117K/year additional revenue)</span>
                            </p>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Who We're Looking For */}
            <div className="bg-gray-50 dark:bg-gray-900 py-16 px-4">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-3xl font-bold mb-4">Who We're Looking For</h2>
                    <p className="text-muted-foreground mb-8">
                        Ideal partners are already serving food companies on compliance matters
                    </p>
                    <div className="flex flex-wrap gap-3 justify-center">
                        {TARGET_PARTNERS.map((partner) => (
                            <Badge key={partner} variant="secondary" className="text-sm py-2 px-4">
                                {partner}
                            </Badge>
                        ))}
                    </div>
                </div>
            </div>

            {/* CTA Section */}
            <div className="py-16 px-4">
                <div className="max-w-3xl mx-auto text-center">
                    <Card className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white border-0">
                        <CardContent className="py-12">
                            <Handshake className="h-12 w-12 mx-auto mb-4" />
                            <h2 className="text-2xl font-bold mb-4">
                                Ready to Scale Your Practice?
                            </h2>
                            <p className="text-white/90 mb-8">
                                Schedule a 30-minute call to discuss how RegEngine can help you
                                serve more clients without adding headcount.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link href="mailto:partners@regengine.co?subject=Partner%20Program%20Demo%20Request">
                                    <Button size="lg" className="bg-white text-blue-700 hover:bg-white/90">
                                        <Mail className="mr-2 h-4 w-4" />
                                        Schedule Partner Call
                                    </Button>
                                </Link>
                                <Link href="/ftl-checker">
                                    <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                        <FileText className="mr-2 h-4 w-4" />
                                        Try FTL Checker First
                                    </Button>
                                </Link>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
