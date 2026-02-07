import Link from 'next/link';
import { Zap, TrendingUp, Cpu, Atom, ArrowRight, Factory, Car, Plane, Building2, Heart, Gamepad } from 'lucide-react';

export default function VerticalsPage() {
    const verticals = [
        {
            name: 'Energy',
            slug: 'energy',
            icon: Zap,
            color: 'blue',
            gradient: 'from-blue-600 to-indigo-700',
            framework: 'NERC CIP-013',
            description: 'Grid compliance and cybersecurity',
            tagline: 'First CIP-013 compliance snapshot in 5 minutes. Not 5 weeks.',
            features: [
                'Immutable compliance snapshots',
                'Substation monitoring',
                'ESP configuration tracking',
                'Chain integrity verification'
            ]
        },
        {
            name: 'Finance',
            slug: 'finance',
            icon: TrendingUp,
            color: 'emerald',
            gradient: 'from-emerald-600 to-teal-700',
            framework: 'SEC / SOX 404',
            description: 'Financial compliance & reporting',
            tagline: 'First SEC filing verification in 5 minutes. Not 5 weeks.',
            features: [
                'SEC filing verification',
                'Real-time regulation monitoring',
                'Compliance scoring',
                'Audit trail generation'
            ]
        },
        {
            name: 'Technology',
            slug: 'technology',
            icon: Cpu,
            color: 'purple',
            gradient: 'from-purple-600 to-pink-700',
            framework: 'SOC 2 / ISO 27001',
            description: 'Security & infrastructure compliance',
            tagline: 'First SOC 2 control verification in 5 minutes. Not 5 weeks.',
            features: [
                'Security control verification',
                'Configuration drift detection',
                'GitOps integration',
                'Continuous monitoring'
            ]
        },
        {
            name: 'Nuclear',
            slug: 'nuclear',
            icon: Atom,
            color: 'orange',
            gradient: 'from-orange-600 to-red-700',
            framework: '10 CFR (NRC)',
            description: 'Nuclear regulatory compliance',
            tagline: 'First NRC-compliant evidence record in 5 minutes. Not 5 weeks.',
            features: [
                'Cryptographic immutability',
                'Fail-safe integrity mode',
                'Legal hold support',
                'NRC inspection ready'
            ]
        },
        {
            name: 'Healthcare',
            slug: 'healthcare',
            icon: Heart,
            color: 'rose',
            gradient: 'from-rose-600 to-pink-700',
            framework: 'HIPAA / HITECH',
            description: 'Healthcare compliance & privacy',
            tagline: 'First HIPAA-compliant audit trail in 5 minutes. Not 5 weeks.',
            features: [
                'Clinical risk monitoring',
                'Patient privacy protection',
                'Breach detection',
                'Compliance dashboards'
            ]
        },
        {
            name: 'Gaming',
            slug: 'gaming',
            icon: Gamepad,
            color: 'violet',
            gradient: 'from-violet-600 to-purple-700',
            framework: 'Gaming Regulations',
            description: 'Gaming industry compliance',
            tagline: 'First gaming compliance snapshot in 5 minutes. Not 5 weeks.',
            features: [
                'Responsible gambling controls',
                'Player protection monitoring',
                'Regulatory reporting',
                'Audit trail generation'
            ]
        },
        {
            name: 'Manufacturing',
            slug: 'manufacturing',
            icon: Factory,
            color: 'gray',
            gradient: 'from-gray-700 to-gray-900',
            framework: 'ISO 9001 / 14001 / 45001',
            description: 'Quality, environmental & safety compliance',
            tagline: 'Triple-certification compliance in one API',
            features: [
                'Immutable NCR tracking',
                'Supplier audit records',
                'ISO gap analysis',
                'Multi-standard snapshots'
            ]
        },
        {
            name: 'Automotive',
            slug: 'automotive',
            icon: Car,
            color: 'red',
            gradient: 'from-red-600 to-orange-600',
            framework: 'IATF 16949 / PPAP',
            description: 'Automotive quality & OEM compliance',
            tagline: 'Cryptographic PPAP packages. OEM-ready.',
            features: [
                '18-element PPAP submission',
                'Layered process audits',
                '8D problem solving',
                'Control plan management'
            ]
        },
        {
            name: 'Aerospace',
            slug: 'aerospace',
            icon: Plane,
            color: 'sky',
            gradient: 'from-sky-600 to-blue-700',
            framework: 'AS9100 / AS9102',
            description: 'Aerospace quality & FAI compliance',
            tagline: 'Immutable first article inspections',
            features: [
                'AS9102 FAI reports',
                'Configuration baselines',
                'NADCAP evidence vault',
                'Counterfeit prevention'
            ]
        },
        {
            name: 'Construction',
            slug: 'construction',
            icon: Building2,
            color: 'amber',
            gradient: 'from-amber-600 to-orange-700',
            framework: 'ISO 19650 / BIM',
            description: 'Construction safety & BIM compliance',
            tagline: 'Cryptographic BIM change logs. OSHA-ready.',
            features: [
                'BIM design change tracking',
                'Safety inspection records',
                'Toolbox talk verification',
                'Multi-standard snapshots'
            ]
        }
    ];

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            {/* Hero Section */}
            <div className="bg-gradient-to-r from-gray-900 to-gray-800 dark:from-black dark:to-gray-900">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                    <div className="text-center">
                        <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                            Compliance APIs for
                            <br />
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-purple-400 to-orange-400">
                                Every Industry
                            </span>
                        </h1>
                        <p className="text-xl text-gray-300 mb-8 max-w-3xl mx-auto">
                            Developer-first compliance infrastructure. Pick your vertical, integrate in minutes,
                            and focus on building your product—not wrestling with regulations.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4 justify-center">
                            <Link
                                href="/api-keys"
                                className="px-8 py-4 bg-white text-gray-900 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
                            >
                                Get API Key
                            </Link>
                            <Link
                                href="/docs"
                                className="px-8 py-4 bg-gray-700 text-white rounded-lg font-semibold hover:bg-gray-600 transition-colors"
                            >
                                View Documentation
                            </Link>
                        </div>
                    </div>
                </div>
            </div>

            {/* Verticals Grid */}
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                <div className="text-center mb-12">
                    <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                        Choose Your Vertical
                    </h2>
                    <p className="text-lg text-gray-600 dark:text-gray-400">
                        Industry-specific compliance APIs designed for developers
                    </p>
                </div>

                <div className="grid md:grid-cols-2 gap-8">
                    {verticals.map((vertical) => {
                        const Icon = vertical.icon;
                        return (
                            <Link
                                key={vertical.slug}
                                href={`/verticals/${vertical.slug}`}
                                className="group relative bg-white dark:bg-gray-800 rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 overflow-hidden border border-gray-200 dark:border-gray-700"
                            >
                                {/* Gradient Background */}
                                <div className={`absolute inset-0 bg-gradient-to-br ${vertical.gradient} opacity-0 group-hover:opacity-5 transition-opacity duration-300`}></div>

                                {/* Content */}
                                <div className="relative p-8">
                                    {/* Header */}
                                    <div className="flex items-start justify-between mb-6">
                                        <div className="flex items-center gap-4">
                                            <div className={`p-3 bg-${vertical.color}-100 dark:bg-${vertical.color}-900 rounded-lg`}>
                                                <Icon className={`h-8 w-8 text-${vertical.color}-600 dark:text-${vertical.color}-400`} />
                                            </div>
                                            <div>
                                                <h3 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                                    {vertical.name}
                                                </h3>
                                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                                    {vertical.framework}
                                                </p>
                                            </div>
                                        </div>
                                        <ArrowRight className="h-6 w-6 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300 group-hover:translate-x-1 transition-all" />
                                    </div>

                                    {/* Description */}
                                    <p className="text-gray-600 dark:text-gray-300 mb-6">
                                        {vertical.description}
                                    </p>

                                    {/* Tagline */}
                                    <p className="text-sm text-gray-500 dark:text-gray-400 italic mb-6">
                                        "{vertical.tagline}"
                                    </p>

                                    {/* Features */}
                                    <div className="space-y-2">
                                        {vertical.features.map((feature, idx) => (
                                            <div key={idx} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                                                <div className={`w-1.5 h-1.5 rounded-full bg-${vertical.color}-500`}></div>
                                                <span>{feature}</span>
                                            </div>
                                        ))}
                                    </div>

                                    {/* CTA */}
                                    <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                                        <span className={`text-sm font-semibold text-${vertical.color}-600 dark:text-${vertical.color}-400 group-hover:underline`}>
                                            Explore {vertical.name} API →
                                        </span>
                                    </div>
                                </div>
                            </Link>
                        );
                    })}
                </div>
            </div>

            {/* Features Section */}
            <div className="bg-white dark:bg-gray-800 py-16">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                            Built for Developers
                        </h2>
                        <p className="text-lg text-gray-600 dark:text-gray-400">
                            Every vertical includes the same developer-first experience
                        </p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-8">
                        <div className="text-center">
                            <div className="inline-flex items-center justify-center w-12 h-12 bg-blue-100 dark:bg-blue-900 rounded-lg mb-4">
                                <svg className="h-6 w-6 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                            </div>
                            <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                5-Minute Quickstart
                            </h3>
                            <p className="text-gray-600 dark:text-gray-400">
                                Install, authenticate, and start recording compliance events in under 5 minutes
                            </p>
                        </div>

                        <div className="text-center">
                            <div className="inline-flex items-center justify-center w-12 h-12 bg-purple-100 dark:bg-purple-900 rounded-lg mb-4">
                                <svg className="h-6 w-6 text-purple-600 dark:text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                                </svg>
                            </div>
                            <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                Type-Safe SDKs
                            </h3>
                            <p className="text-gray-600 dark:text-gray-400">
                                First-class SDKs for Node.js, Python, and Go with full TypeScript support
                            </p>
                        </div>

                        <div className="text-center">
                            <div className="inline-flex items-center justify-center w-12 h-12 bg-green-100 dark:bg-green-900 rounded-lg mb-4">
                                <svg className="h-6 w-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                            </div>
                            <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                Cryptographic Audit Trail
                            </h3>
                            <p className="text-gray-600 dark:text-gray-400">
                                SHA-256 verified compliance records with independently verifiable integrity
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            {/* CTA Section */}
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                <div className="bg-gradient-to-r from-blue-600 via-purple-600 to-orange-600 rounded-2xl p-12 text-center">
                    <h2 className="text-3xl font-bold text-white mb-4">
                        Ready to build compliant software?
                    </h2>
                    <p className="text-xl text-blue-100 mb-8">
                        Choose your vertical and get API access in seconds
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link
                            href="/api-keys"
                            className="px-8 py-4 bg-white text-gray-900 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
                        >
                            Get Free API Key
                        </Link>
                        <Link
                            href="/pricing"
                            className="px-8 py-4 bg-white/20 text-white rounded-lg font-semibold hover:bg-white/30 transition-colors border border-white/20"
                        >
                            View Pricing
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
