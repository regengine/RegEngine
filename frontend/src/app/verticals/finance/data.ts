import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const financeIndustryData = {
    industry: 'Finance & FinTech',
    description: `Financial services face dual compliance pressures: SOC 2 Type II for enterprise customer trust and PCI DSS for payment processing. With 83% of companies requiring SOC 2 audits from vendors (Vanta, 2024), becoming "audit-ready" is now a market prerequisite. Yet compliance is often treated as a checkbox rather than security posture—companies pass audits but still get breached. SOC 2 audits cost $50K-150K annually and require 3-12 months of continuous evidence collection.`,

    regulations: [
        {
            name: 'SOC 2 Type II',
            shortName: 'SOC 2',
            description: 'Trust Services Criteria covering Security, Availability, Processing Integrity, Confidentiality, and Privacy. Requires 3-12 months of continuous evidence.',
            authority: 'American Institute of CPAs (AICPA)',
        },
        {
            name: 'PCI DSS v4.0',
            shortName: 'PCI DSS',
            description: 'Payment Card Industry Data Security Standard. Mandates network segmentation, encryption, access controls, and vulnerability management for cardholder data.',
            authority: 'PCI Security Standards Council',
        },
        {
            name: 'GLBA (Gramm-Leach-Bliley Act)',
            shortName: 'GLBA',
            description: 'Requires financial institutions to explain information sharing practices and protect sensitive customer data.',
            authority: 'Federal Trade Commission (FTC)',
        },
        {
            name: 'GDPR',
            shortName: 'GDPR',
            description: 'General Data Protection Regulation for EU customer data. Fines up to 4% of global revenue for non-compliance.',
            authority: 'European Commission',
        },
        {
            name: 'ISO 20022',
            shortName: 'ISO 20022',
            description:
                'Universal Financial Industry message scheme. Global standard for financial messaging adopted by central banks and SWIFT for cross-border payments. Enables faster, more accurate transfers with richer data, reducing errors and processing costs.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 22301:2019',
            shortName: 'ISO 22301',
            description:
                'Business Continuity Management Systems - Requirements. Critical for financial services resilience. Banks with ISO 22301 certification demonstrated seamless remote operations during COVID-19. ~40,000 certifications worldwide.',
            authority: 'International Organization for Standardization (ISO)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'Manual Evidence Collection',
            description: 'Auditors request screenshots of firewall rules, access logs, penetration test reports. Teams spend weeks manually gathering evidence from disparate systems.',
            impact: 'high',
        },
        {
            title: 'Point-in-Time vs Continuous Compliance',
            description: 'SOC 2 Type II requires continuous monitoring over 3-12 months, but most tools only provide point-in-time snapshots. Gap between audits = compliance drift.',
            impact: 'high',
        },
        {
            title: 'Change Control Documentation',
            description: 'Cannot prove "when" a security control was implemented. Auditors ask: "Show me your firewall config on June 15th." Excel version control is insufficient.',
            impact: 'medium',
        },
        {
            title: 'Vendor Risk Management',
            description: 'Must track SOC 2 reports for 100+ SaaS vendors. Manual spreadsheet tracking is error-prone. No automated expiration alerts.',
            impact: 'medium',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'Compliance Automation Platforms',
            examples: ['Vanta', 'Drata', 'Secureframe'],
            pros: ['Screenshot automation', 'Vendor tracking', 'Audit checklists', 'Auditor portal'],
            cons: ['Not developer-first', 'Evidence is mutable screenshots', 'No cryptographic verification', 'Expensive ($15K-40K/year)'],
            typicalCost: '$15K-40K/year',
        },
        {
            category: 'Traditional SOC 2 Auditors',
            examples: ['Big 4 Firms', 'Schellman', 'A-LIGN'],
            pros: ['Full-service', 'Industry credibility', 'Established processes'],
            cons: ['Manual processes', 'Expensive ($50K-150K per audit)', '4-6 month cycles', 'Limited continuous monitoring'],
            typicalCost: '$50K-150K/audit',
        },
        {
            category: 'GRC Platforms',
            examples: ['ServiceNow GRC', 'Archer', 'OneTrust'],
            pros: ['Enterprise workflows', 'Control mapping', 'Risk registers'],
            cons: ['Not finance-specific', 'Expensive ($100K+/year)', 'Long implementations', 'No immutable evidence'],
            typicalCost: '$100K-300K/year',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Immutable evidence snapshots with cryptographic verification',
            'API-driven: Automated evidence collection (minutes, not weeks)',
            '5-minute integration vs 2-week onboarding',
            'Version control for security configs (prove "when" a control existed)',
            'Cost-effective: $2K-8K/month vs $50K+ audits',
        ],
        tradeoffs: [
            'Requires technical implementation (not point-and-click)',
            'Self-service model (less hand-holding than full-service auditors)',
            'Works best with cloud-native stacks (API-accessible systems)',
        ],
        notFor: [
            'Non-technical compliance teams without developer resources',
            'Organizations requiring full-service audit consulting',
            'Legacy on-premise environments without APIs',
        ],
    } as ApproachComparison,
};


export const financeApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/finance/evidence-snapshots',
        description: 'Create an immutable SOC 2 evidence snapshot for a security control',
        category: 'Evidence Management',
        requiresAuth: true,
        requestExample: `curl -X POST https://api.regengine.co/v1/finance/evidence-snapshots \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "control_id": "CC1.2",
    "control_name": "MFA Required for Admin Access",
    "evidence_type": "IDENTITY_POLICY",
    "evidence_data": {
      "policy_name": "AdminRequiresMFA",
      "policy_reference": "identity/policies/AdminMFA",
      "mfa_required": true,
      "enabled": true
    },
    "audit_period": "2024-Q1",
    "timestamp": "2024-01-26T10:00:00Z"
  }'`,
        responseExample: `{
  "snapshot_id": "evid_0193f8a7b2c4d5e6",
  "control_id": "CC1.2",
  "content_hash": "sha256:a3f5b8c9d2e1f4a7...",
  "sealed": true,
  "created_at": "2024-01-26T10:00:01Z",
  "audit_ready": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/finance/evidence-snapshots/:id',
        description: 'Retrieve a specific evidence snapshot by ID',
        category: 'Evidence Management',
        requiresAuth: true,
        responseExample: `{
  "snapshot_id": "evid_0193f8a7b2c4d5e6",
  "control_id": "CC1.2",
  "control_name": "MFA Required for Admin Access",
  "evidence_type": "IDENTITY_POLICY",
  "content_hash": "sha256:a3f5b8c9d2e1f4a7...",
  "sealed": true,
  "created_at": "2024-01-26T10:00:01Z",
  "audit_ready": true
}`,
    },
    {
        method: 'POST',
        path: '/v1/finance/evidence-snapshots/:id/verify',
        description: 'Cryptographically verify evidence snapshot integrity',
        category: 'Verification',
        requiresAuth: true,
        responseExample: `{
  "snapshot_id": "evid_0193f8a7b2c4d5e6",
  "is_valid": true,
  "chain_valid": true,
  "verification_method": "sha256",
  "verified_at": "2024-01-26T10:05:00Z",
  "tampered": false
}`,
    },
    {
        method: 'GET',
        path: '/v1/finance/vendor-risk',
        description: 'Get vendor SOC 2 certification status and risk scores',
        category: 'Vendor Management',
        requiresAuth: true,
        responseExample: `{
  "vendors": [
    {
      "vendor_id": "vnd_stripe",
      "name": "Stripe",
      "soc2_type": "TYPE_II",
      "soc2_expiration": "2024-12-31",
      "risk_score": 15,
      "status": "COMPLIANT"
    },
    {
      "vendor_id": "vnd_cloud_host",
      "name": "Cloud Hosting Provider",
      "soc2_type": "TYPE_II",
      "soc2_expiration": "2024-11-30",
      "risk_score": 10,
      "status": "COMPLIANT"
    }
  ],
  "total": 2,
  "high_risk_count": 0
}`,
    },
    {
        method: 'POST',
        path: '/v1/finance/audit-export',
        description: 'Export SOC 2 audit report with all evidence snapshots',
        category: 'Audit & Reporting',
        requiresAuth: true,
        requestExample: `{
  "audit_period": "2024-Q1",
  "controls": ["CC1.1", "CC1.2", "CC1.3"],
  "format": "PDF"
}`,
        responseExample: `{
  "export_id": "exp_0193f8a7b2c4d5e6",
  "status": "GENERATING",
  "download_url": null,
  "estimated_completion": "2024-01-26T10:15:00Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/finance/iso-20022-validation',
        description: 'Validate financial messages against ISO 20022 schema',
        category: 'ISO Compliance',
        requiresAuth: true,
        requestExample: `{
  "message_type": "pacs.008.001.08",
  "message_data": {
    "fi_to_fi_payment": {
      "transaction_id": "TXN20240126001",
      "amount": 10000.50,
      "currency": "USD",
      "debtor": {"name": "Acme Corp", "account": "123456789"},
      "creditor": {"name": "Widget LLC", "account": "987654321"}
    }
  }
}`,
        responseExample: `{
  "validation_id": "iso20022_0193f8a7b2c4d5e6",
  "message_type": "pacs.008.001.08",
  "is_valid": true,
  "schema_version": "2019",
  "enriched_data_fields": 15,
  "processing_improvements": "Faster reconciliation, reduced manual intervention"
}`,
    },
    {
        method: 'GET',
        path: '/v1/finance/iso-22301-bcm-status',
        description: 'Get ISO 22301 business continuity management readiness status',
        category: 'ISO Compliance',
        requiresAuth: true,
        responseExample: `{
  "standard": "ISO 22301:2019",
  "certification_status": "IN_PROGRESS",
  "overall_readiness": 82,
  "business_impact_analysis": "COMPLETE",
  "recovery_strategies": "COMPLETE",
  "bc_plan_testing": "PARTIAL",
  "next_drill_date": "2024-02-15",
  "last_incident_recovery_time": "4_HOURS",
  "target_recovery_time": "2_HOURS"
}`,
    },
];

export const financeSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/finance-sdk',
        description: 'Type-safe SDK for SOC 2 compliance automation',
        quickstartCode: `import { FinanceCompliance } from '@regengine/finance-sdk';

const finance = new FinanceCompliance('rge_your_api_key');

// Create evidence snapshot
const snapshot = await finance.evidenceSnapshots.create({
  control_id: 'CC1.2',
  control_name: 'MFA Required for Admin Access',
  evidence_type: 'IDENTITY_POLICY',
  evidence_data: {
    policy_name: 'AdminRequiresMFA',
    mfa_required: true,
    enabled: true
  },
  audit_period: '2024-Q1'
});

console.log('✅ Evidence snapshot created:', snapshot.snapshot_id);
console.log('🔒 Content hash:', snapshot.content_hash);
console.log('📋 Audit ready:', snapshot.audit_ready);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-finance',
        description: 'Python SDK for SOC 2 evidence collection',
        quickstartCode: `from regengine.finance import FinanceCompliance

finance = FinanceCompliance(api_key= 'rge_your_api_key')

# Create evidence snapshot
snapshot = finance.evidence_snapshots.create(
    control_id='CC1.2',
    control_name='MFA Required for Admin Access',
    evidence_type='IDENTITY_POLICY',
    evidence_data={
        'policy_name': 'AdminRequiresMFA',
        'mfa_required': True,
        'enabled': True
    },
    audit_period='2024-Q1'
)

print(f'✅ Evidence snapshot: {snapshot.snapshot_id}')
print(f'🔒 Content hash: {snapshot.content_hash}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/finance-sdk-go',
        description: 'Go SDK for high-performance compliance automation',
        quickstartCode: `package main

import (
    "github.com/regengine/finance-sdk-go"
)

func main() {
    client := finance.NewClient("rge_your_api_key")
    
    snapshot, err := client.EvidenceSnapshots.Create(&finance.EvidenceRequest{
        ControlID: "CC1.2",
        ControlName: "MFA Required for Admin Access",
        EvidenceType: "IDENTITY_POLICY",
        AuditPeriod: "2024-Q1",
    })
    
    if err != nil {
        panic(err)
    }
    
    fmt.Printf("Snapshot: %s\\n", snapshot.ID)
}`,
    },
];
