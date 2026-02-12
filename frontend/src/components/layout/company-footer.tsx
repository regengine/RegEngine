'use client';

import Link from 'next/link';
import { Activity } from 'lucide-react';

const footerLinks = {
    product: [
        { label: 'Field Capture', href: '/mobile/capture', badge: 'New' },
        { label: 'Compliance Snapshots', href: '/compliance/snapshots', badge: 'New' },
        { label: 'Ingest Documents', href: '/ingest' },
        { label: 'FTL Coverage Checker', href: '/ftl-checker', badge: 'Free' },
        { label: 'Pricing', href: '/pricing' },
        { label: 'Mock Recall Demo', href: '/demo/mock-recall' },
        { label: 'Supply Chain Explorer', href: '/demo/supply-chains', badge: 'New' },
        { label: 'FSMA 204 Dashboard', href: '/fsma' },
    ],
    solutions: [
        { label: 'Retailer Readiness', href: '/retailer-readiness' },
        { label: 'Partner Program', href: '/partners' },
        { label: 'Sales Resources', href: '/resources' },
    ],
    developers: [
        { label: 'API Documentation', href: '/docs' },
        { label: 'Developer Portal', href: '/developers' },
        { label: 'Get Started', href: '/onboarding' },
    ],
};

export function CompanyFooter() {
    return (
        <footer className="bg-gray-900 text-gray-400 py-8 mt-auto">
            <div className="max-w-6xl mx-auto px-4">
                <div className="grid grid-cols-2 md:grid-cols-12 gap-8">
                    {/* Brand - 4 columns  */}
                    <div className="col-span-2 md:col-span-4">
                        <Link href="/" className="flex items-center gap-2 text-white mb-3">
                            <Activity className="h-5 w-5 text-emerald-500" />
                            <span className="text-lg font-bold">RegEngine</span>
                        </Link>
                        <p className="text-sm text-gray-500">
                            API-first FSMA 204 compliance platform
                        </p>
                    </div>

                    {/* Product - 3 columns */}
                    <div className="col-span-1 md:col-span-3">
                        <h4 className="text-white font-medium text-sm mb-3">Product</h4>
                        <ul className="space-y-2">
                            {footerLinks.product.map((link) => (
                                <li key={link.href}>
                                    <Link href={link.href} className="text-sm hover:text-white transition-colors flex items-center gap-2">
                                        {link.label}
                                        {link.badge && (
                                            <span className="text-xs bg-emerald-600 text-white px-1.5 py-0.5 rounded">
                                                {link.badge}
                                            </span>
                                        )}
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    </div>

                    {/* Solutions - 3 columns */}
                    <div className="col-span-1 md:col-span-2">
                        <h4 className="text-white font-medium text-sm mb-3">Solutions</h4>
                        <ul className="space-y-2">
                            {footerLinks.solutions.map((link) => (
                                <li key={link.href}>
                                    <Link href={link.href} className="text-sm hover:text-white transition-colors">
                                        {link.label}
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    </div>

                    {/* Developers - 3 columns */}
                    <div className="col-span-1 md:col-span-3">
                        <h4 className="text-white font-medium text-sm mb-3">Developers</h4>
                        <ul className="space-y-2">
                            {footerLinks.developers.map((link) => (
                                <li key={link.href}>
                                    <Link href={link.href} className="text-sm hover:text-white transition-colors">
                                        {link.label}
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>

                {/* Bottom bar */}
                <div className="border-t border-gray-800 mt-8 pt-6 flex flex-col md:flex-row justify-between items-center gap-4 text-xs text-gray-500">
                    <p>
                        © {new Date().getFullYear()} RegEngine. All rights reserved.
                    </p>
                    <p>
                        <span className="font-semibold text-gray-400">FSMA 204 Deadline: July 20, 2028</span>
                        {' '} | FDA Food Traceability Rule
                    </p>
                </div>
            </div>
        </footer>
    );
}
