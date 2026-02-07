'use client';

import { motion } from 'framer-motion';
import {
    Shield,
    FileText,
    Activity,
    Lock,
    Zap,
    Server,
    ArrowLeft,
    PlayCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';
import { useState } from 'react';

const FRAMEWORKS = [
    {
        id: 'healthcare',
        title: 'Healthcare',
        icon: Activity,
        description: 'HIPAA, HITECH, FDA 21 CFR Part 11',
        details: 'Protect patient privacy and ensure clinical safety with pre-built controls for ePHI, audit logs, and medical device security.',
        jsonSnippet: `{
  "rule_pack_id": "healthcare_hipaa_v1",
  "rules": [
    {
      "requirement": "Risk Management Process",
      "severity": "CRITICAL",
      "checklist_item": "Conduct thorough assessments of potential vulnerabilities to ePHI..."
    }
  ]
}`
    },
    {
        id: 'finance',
        title: 'Finance',
        icon: Lock,
        description: 'PCI DSS 4.0, SOX, GLBA',
        details: 'Secure transactional integrity with automated checks for encryption, access control, and financial reporting accuracy.',
        jsonSnippet: `{
  "rule_pack_id": "finance_pci_sox_v1",
  "rules": [
    {
      "requirement": "Network Security",
      "severity": "CRITICAL",
      "checklist_item": "Install firewalls; deny unauthorized traffic; encrypt card data..."
    }
  ]
}`
    },
    {
        id: 'gaming',
        title: 'Gaming',
        icon: FileText,
        description: 'AML/KYC, GLI-11, GLI-19',
        details: 'Ensure fairness and counter financial crime with real-time monitoring for money laundering and RNG certification.',
        jsonSnippet: `{
  "rule_pack_id": "gaming_aml_gli_v1",
  "rules": [
    {
      "requirement": "Customer Due Diligence",
      "severity": "CRITICAL",
      "checklist_item": "Verify ID with liveness detection; screen for Politically Exposed Persons (PEPs)..."
    }
  ]
}`
    },
    {
        id: 'energy',
        title: 'Energy',
        icon: Zap,
        description: 'NERC CIP',
        details: 'Protect critical infrastructure with IT/OT integration, asset categorization, and electronic security perimeters.',
        jsonSnippet: `{
  "rule_pack_id": "energy_nerc_cip_v1",
  "rules": [
    {
      "requirement": "ESP Management",
      "severity": "CRITICAL",
      "checklist_item": "Define ESP boundaries; implement layered zones in control centers..."
    }
  ]
}`
    },
    {
        id: 'technology',
        title: 'Technology',
        icon: Server,
        description: 'SOC 2, ISO 27001, GDPR',
        details: 'Demonstrate governance and trust with mapped controls for data privacy, security maturity, and evidence collection.',
        jsonSnippet: `{
  "rule_pack_id": "tech_soc2_iso_gdpr_v1",
  "rules": [
    {
      "requirement": "Trust Services Criteria",
      "severity": "HIGH",
      "checklist_item": "Address the 'Common Criteria' (Security) through risk assessment..."
    }
  ]
}`
    }
];

function CodeBlock({ code }: { code: string }) {
    return (
        <pre className="bg-gray-950 text-gray-300 p-4 rounded-lg overflow-x-auto text-xs font-mono border border-gray-800">
            <code>{code}</code>
        </pre>
    );
}

export default function ComplianceVerticalsPage() {
    return (
        <div className="min-h-screen bg-gray-950 text-gray-100">
            <div className="border-b border-gray-800 py-16 px-4">
                <div className="max-w-4xl mx-auto">
                    <Link href="/developers" className="inline-flex items-center text-gray-400 hover:text-white mb-8 transition-colors">
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Back to Developers
                    </Link>

                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                    >
                        <Badge className="mb-4 bg-purple-500/20 text-purple-400 border-purple-500/50">
                            New Feature
                        </Badge>
                        <h1 className="text-4xl md:text-5xl font-bold mb-4">
                            Strategic Compliance<br />
                            <span className="text-purple-400">Vertical Frameworks</span>
                        </h1>
                        <p className="text-xl text-gray-400 max-w-2xl">
                            Pre-built, architectural-grade RulePacks for highly regulated industries.
                            Start with a baseline of verified controls.
                        </p>
                    </motion.div>
                </div>
            </div>

            <div className="max-w-6xl mx-auto px-4 py-16">
                <div className="grid gap-8">
                    {FRAMEWORKS.map((fw, i) => (
                        <motion.div
                            key={fw.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.1 }}
                        >
                            <Card className="bg-gray-900 border-gray-800 overflow-hidden">
                                <div className="grid md:grid-cols-2">
                                    <div className="p-6 md:p-8 flex flex-col justify-center">
                                        <div className="flex items-center gap-3 mb-4">
                                            <div className="p-2 bg-purple-500/20 rounded-lg">
                                                <fw.icon className="h-6 w-6 text-purple-400" />
                                            </div>
                                            <h2 className="text-2xl font-bold">{fw.title}</h2>
                                        </div>
                                        <div className="text-sm font-mono text-purple-400 mb-4">
                                            {fw.description}
                                        </div>
                                        <p className="text-gray-400 mb-6">
                                            {fw.details}
                                        </p>
                                        <div className="flex gap-4">
                                            <Button variant="outline" className="border-gray-700 hover:bg-gray-800">
                                                View Standard
                                            </Button>
                                            <Button className="bg-purple-600 hover:bg-purple-700">
                                                Load RulePack
                                            </Button>
                                        </div>
                                    </div>
                                    <div className="bg-gray-950 p-6 md:p-8 border-l border-gray-800">
                                        <div className="flex items-center justify-between mb-4">
                                            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                                Example Seed Data
                                            </span>
                                            <Badge variant="outline" className="text-xs border-gray-700 text-gray-500">
                                                JSON
                                            </Badge>
                                        </div>
                                        <CodeBlock code={fw.jsonSnippet} />
                                    </div>
                                </div>
                            </Card>
                        </motion.div>
                    ))}
                </div>
            </div>

            <div className="border-t border-gray-800 py-16 px-4 text-center">
                <Shield className="h-12 w-12 text-gray-700 mx-auto mb-4" />
                <h3 className="text-xl font-bold text-gray-300 mb-2">Enterprise Grade</h3>
                <p className="text-gray-500 max-w-md mx-auto">
                    All frameworks are aligned with the foundational pillars of Risk Assessment,
                    Policy Development, and Continuous Improvement.
                </p>
            </div>
        </div>
    );
}
