import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const manufacturingIndustryData = {
    industry: 'Manufacturing',
    description: `The manufacturing sector manages 291,000+ facilities across the United States alone, producing $6.3 trillion in annual output. With global supply chains spanning 100+ countries and stringent quality requirements, manufacturers face immense pressure to maintain ISO 9001 (quality), ISO 14001 (environmental), and ISO 45001 (safety) certifications simultaneously. Traditional compliance requires manual audits, paper-based documentation, and multi-week evidence compilation—creating operational risks, audit failures, and $500K+ annual compliance costs for mid-sized operations.`,

    regulations: [
        {
            name: 'ISO 9001:2015',
            shortName: 'ISO 9001',
            description:
                'Quality Management Systems - Requirements. The global standard for quality management with 1+ million certifications worldwide. Mandates process control, risk-based thinking, and continuous improvement. Required for aerospace, automotive, and defense supply chains.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 14001:2015',
            shortName: 'ISO 14001',
            description:
                'Environmental Management Systems - Requirements. Enables systematic environmental impact reduction, waste minimization, and regulatory compliance. 450,000+ certifications globally. Mandatory for EU market access and corporate ESG commitments.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 45001:2018',
            shortName: 'ISO 45001',
            description:
                'Occupational Health and Safety Management - Requirements. Replaced OHSAS 18001 globally. Reduces workplace injuries by 30-50%. Critical for insurance rates, liability protection, and regulatory compliance across 100+ jurisdictions.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'FDA 21 CFR Part 820',
            shortName: 'QSR',
            description:
                'Quality System Regulation for medical device manufacturers. Harmonized with ISO 13485. Failure results in warning letters, product recalls, and facility shutdown.',
            authority: 'U.S. Food and Drug Administration (FDA)',
        },
        {
            name: 'IATF 16949:2016',
            shortName: 'IATF 16949',
            description:
                'Automotive quality management standard built on ISO 9001. Required by all major OEMs (GM, Ford, Toyota, VW). 70,000+ certified suppliers globally.',
            authority: 'International Automotive Task Force (IATF)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'Triple-Certification Chaos',
            description:
                'Manufacturers need simultaneous ISO 9001 + 14001 + 45001 compliance. Separate audit cycles. Overlapping requirements tracked in different systems. No unified audit trail.',
            impact: 'high',
        },
        {
            title: 'Non-Conformance Tracking Nightmare',
            description:
                'Excel spreadsheets for NCRs (Non-Conformance Reports) cannot prove when corrective actions were taken. Auditors reject mutable records. Fines and certification suspension.',
            impact: 'high',
        },
        {
            title: 'Supply Chain Variability',
            description:
                '100+ suppliers across 20 countries. Each with different quality standards. Manual supplier audits take 6-12 months. Cannot trace root cause of defects.',
            impact: 'medium',
        },
        {
            title: 'Expensive Third-Party Audits',
            description:
                '3 annual surveillance audits (9001, 14001, 45001) at $15K-30K each. Plus recertification every 3 years at $50K+. Audit prep consumes 200+ labor hours.',
            impact: 'high',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'QMS Software',
            examples: ['Qualio', 'MasterControl', 'ETQ Reliance'],
            pros: [
                'Document control',
                'Workflow automation',
                'Training tracking',
                'Change management',
            ],
            cons: [
                'No cryptographic verification',
                'Expensive ($50K-200K/year)',
                'Complex implementation (6-18 months)',
                'Poor multi-standard integration',
            ],
            typicalCost: '$50K-200K/year',
        },
        {
            category: 'Certification Consultancies',
            examples: ['BSI', 'TÜV', 'DNV', 'SGS'],
            pros: [
                'Expert auditors',
                'Global certification body',
                'Gap analysis services',
            ],
            cons: [
                'Purely audit-focused (no tech)',
                'Manual evidence review',
                'Expensive ($75K-150K per standard)',
                '12-24 month certification timeline',
            ],
            typicalCost: '$150K-300K/year (all 3 standards)',
        },
        {
            category: 'DIY Solutions',
            examples: ['SharePoint', 'Excel', 'Paper Binders'],
            pros: ['Low initial cost', 'Familiar tools', 'Full control'],
            cons: [
                'Cannot prove integrity',
                'Audit failures',
                'No automated evidence',
                'Unmaintainable at scale',
            ],
            typicalCost: '$5K-20K/year (labor)',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Unified API for all 3 ISO standards (9001, 14001, 45001)',
            'Cryptographic NCR trail: Prove exactly when corrective actions occurred',
            'Automated surveillance readiness: Real-time compliance snapshots',
            '80% faster audit prep: API-generated evidence packages',
            'Starting at $4,500/month vs $300K/year consultants + software',
        ],
        tradeoffs: [
            'Requires API integration (not a SaaS click-through)',
            'Best for companies with engineering/IT resources',
            'Certification bodies still required (we provide evidence, not certification)',
        ],
        notFor: [
            'Manufacturers without technical staff',
            'Organizations requiring full consulting services',
            'Companies seeking certification bodies (we complement, not replace)',
        ],
    } as ApproachComparison,
};

export const manufacturingApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/manufacturing/ncr',
        description: 'Create immutable Non-Conformance Report (NCR) with cryptographic audit trail',
        category: 'Quality',
        requiresAuth: true,

        requestExample: `curl -X POST https://api.regengine.co/v1/manufacturing/ncr \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "ncr_id": "NCR-2024-001",
    "product_id": "SKU-12345",
    "defect_type": "DIMENSIONAL_VARIANCE",
    "severity": "MAJOR",
    "root_cause": "Tooling wear beyond tolerance",
    "corrective_action": "Replace tooling, implement hourly inspection",
    "responsible_party": "Quality Engineer - J. Smith",
    "iso_standard": "ISO 9001:2015",
    "clause_reference": "8.7 - Control of nonconforming outputs"
  }'`,
        responseExample: `{
  "id": "ncr_0193f8a7b2c4d5e6",
  "ncr_id": "NCR-2024-001",
  "contentHash": "sha256:d4e1f4a7b3f5a8c9...",
  "chainStatus": "valid",
  "sealed": true,
  "createdAt": "2024-01-26T14:23:00Z",
  "immutable": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/manufacturing/ncr/:id/audit-trail',
        description: 'Retrieve complete audit trail for an NCR with cryptographic verification',
        category: 'Quality',
        requiresAuth: true,
        responseExample: `{
  "ncr_id": "NCR-2024-001",
  "timeline": [
    {
      "event": "NCR_CREATED",
      "timestamp": "2024-01-26T14:23:00Z",
      "hash": "sha256:d4e1f4a7b3f5a8c9...",
      "actor": "Quality Engineer - J. Smith"
    },
    {
      "event": "CORRECTIVE_ACTION_IMPLEMENTED",
      "timestamp": "2024-01-27T09:15:00Z",
      "hash": "sha256:e5f2a8b4c6d9f1a2...",
      "actor": "Production Manager - A. Jones"
    }
  ],
  "chainValid": true,
  "totalEvents": 2
}`,
    },
    {
        method: 'POST',
        path: '/v1/manufacturing/triple-cert-snapshot',
        description: 'Create unified snapshot for ISO 9001 + 14001 + 45001 surveillance readiness',
        category: 'Multi-Standard',
        requiresAuth: true,
        requestExample: `{
  "facility_id": "PLANT-TX-001",
  "snapshot_type": "SURVEILLANCE_AUDIT",
  "standards": ["ISO 9001:2015", "ISO 14001:2015", "ISO 45001:2018"],
  "quality_metrics": {
    "ncr_count_30d": 3,
    "customer_complaints": 0,
    "process_capability_cpk": 1.67
  },
  "environmental_metrics": {
    "waste_reduction_ytd_pct": 12.3,
    "energy_consumption_kwh": 45000,
    "regulatory_violations": 0
  },
  "safety_metrics": {
    "lost_time_incidents": 0,
    "near_misses_reported": 8,
    "safety_training_compliance_pct": 98.5
  }
}`,
        responseExample: `{
  "snapshot_id": "snap_0193f8a7b2c4d5e6",
  "facility_id": "PLANT-TX-001",
  "standards_covered": 3,
  "contentHash": "sha256:a7b3f5a8c9d4e1f4...",
  "auditReady": true,
  "expiresAt": "2024-04-26T14:23:00Z",
  "certificationBodies": ["BSI", "TUV", "DNV"]
}`,
    },
    {
        method: 'GET',
        path: '/v1/manufacturing/iso-9001-gap-analysis',
        description: 'Automated gap analysis against ISO 9001:2015 clauses',
        category: 'Certification',
        requiresAuth: true,
        requestExample: `?facility_id=PLANT-TX-001`,
        responseExample: `{
  "facility_id": "PLANT-TX-001",
  "standard": "ISO 9001:2015",
  "overall_readiness": 87,
  "gaps": [
    {
      "clause": "6.2",
      "requirement": "Quality objectives and planning to achieve them",
      "status": "PARTIAL",
      "recommendation": "Document measurable objectives for customer satisfaction"
    },
    {
      "clause": "9.1.3",
      "requirement": "Analysis and evaluation",
      "status": "MISSING",
      "recommendation": "Implement systematic analysis of quality data trends"
    }
  ],
  "compliant_clauses": 22,
  "total_clauses": 25,
  "estimated_certification_timeline": "6-9 months"
}`,
    },
    {
        method: 'POST',
        path: '/v1/manufacturing/supplier-audit',
        description: 'Record supplier quality audits with cryptographic verification',
        category: 'Supply Chain',
        requiresAuth: true,
        requestExample: `{
  "supplier_id": "SUPP-CN-042",
  "supplier_name": "Precision Components Ltd.",
  "audit_type": "ON_SITE",
  "audit_date": "2024-01-20",
  "auditor": "Lead Auditor - M. Chen",
  "standards_verified": ["ISO 9001:2015"],
  "findings": [
    {
      "clause": "8.5.1",
      "finding_type": "MINOR_NC",
      "description": "Process control charts not updated weekly",
      "corrective_action_required": true
    }
  ],
  "overall_rating": "APPROVED_WITH_CONDITIONS"
}`,
        responseExample: `{
  "audit_id": "aud_0193f8a7b2c4d5e6",
  "supplier_id": "SUPP-CN-042",
  "contentHash": "sha256:f4a7b3f5a8c9d4e1...",
  "sealed": true,
  "followup_required": true,
  "followup_deadline": "2024-03-20"
}`,
    },
];

export const manufacturingSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/manufacturing-sdk',
        description: 'Type-safe SDK for quality management systems',
        quickstartCode: `import { ManufacturingCompliance } from '@regengine/manufacturing-sdk';

const mfg = new ManufacturingCompliance('rge_your_api_key');

// Create NCR with immutable audit trail
const ncr = await mfg.ncr.create({
  ncr_id: 'NCR-2024-001',
  product_id: 'SKU-12345',
  defect_type: 'DIMENSIONAL_VARIANCE',
  severity: 'MAJOR',
  corrective_action: 'Replace tooling, implement hourly inspection',
  iso_standard: 'ISO 9001:2015'
});

console.log('NCR created:', ncr.id);
console.log('Content hash:', ncr.contentHash);
console.log('Immutable:', ncr.sealed);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-manufacturing',
        description: 'Python SDK for ERP and MES integration',
        quickstartCode: `from regengine.manufacturing import ManufacturingCompliance

mfg = ManufacturingCompliance(api_key='rge_your_api_key')

# Create triple-certification snapshot
snapshot = mfg.snapshots.create_triple_cert(
    facility_id='PLANT-TX-001',
    snapshot_type='SURVEILLANCE_AUDIT',
    standards=['ISO 9001:2015', 'ISO 14001:2015', 'ISO 45001:2018'],
    quality_metrics={
        'ncr_count_30d': 3,
        'process_capability_cpk': 1.67
    }
)

print(f'Snapshot ID: {snapshot.snapshot_id}')
print(f'Audit ready: {snapshot.audit_ready}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/manufacturing-sdk-go',
        description: 'Go SDK for high-throughput IoT integration',
        quickstartCode: `package main

import (
    "github.com/regengine/manufacturing-sdk-go"
)

func main() {
    client := manufacturing.NewClient("rge_your_api_key")
    
    ncr, err := client.NCR.Create(&manufacturing.NCRRequest{
        NCRID:      "NCR-2024-001",
        ProductID:  "SKU-12345",
        DefectType: "DIMENSIONAL_VARIANCE",
        Severity:   "MAJOR",
    })
    
    fmt.Printf("NCR sealed: %s\\n", ncr.ContentHash)
}`,
    },
];
