import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const technologyIndustryData = {
    industry: 'Technology & SaaS',
    description: `SaaS companies face a trust gap: 87% of enterprise buyers require SOC 2 or ISO 27001 certification before signing contracts (Tugboat Logic). Yet compliance is often treated as a "checkbox"—companies pass audits but still get breached (see: Okta 2023). The average SaaS company manages 100+ vendor relationships, 50+ security controls, and 3-12 month audit cycles. With delayed contract signatures costing $100K+ in lost revenue, audit readiness is a competitive advantage.`,

    regulations: [
        {
            name: 'SOC 2 Type II',
            shortName: 'SOC 2',
            description: 'AICPA Trust Services Principles. Required by 87% of enterprise buyers. Audit-ready evidence must cover 3-12 months of continuous compliance.',
            authority: 'American Institute of CPAs (AICPA)',
        },
        {
            name: 'ISO/IEC 27001',
            shortName: 'ISO 27001',
            description: 'International standard for information security management systems (ISMS). Requires risk assessments, security policies, and continuous improvement.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'GDPR',
            shortName: 'GDPR',
            description: 'EU data protection regulation. Fines up to €20M or 4% of global revenue. Requires data processing agreements with every vendor.',
            authority: 'European Commission',
        },
        {
            name: 'CCPA/CPRA',
            shortName: 'CCPA',
            description: 'California Consumer Privacy Act. Grants consumers rights to access, delete, and opt-out. Fines up to $7,500 per intentional violation.',
            authority: 'California Attorney General',
        },
        {
            name: 'ISO/IEC 20000-1:2018',
            shortName: 'ISO 20000',
            description:
                'IT Service Management Systems - Requirements. Fastest growing service management standard. Helps technology companies demonstrate operational excellence and reduce support costs. One IT service unit cut support volumes by 20% after implementing ISO 20000.',
            authority: 'International Organization for Standardization (ISO)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'Manual Screenshot Collection',
            description: 'Auditors request screenshots of every config change: AWS IAM policies, GitHub branch protection, firewall rules. Teams spend 40+ hours manually screenshotting.',
            impact: 'high',
        },
        {
            title: 'Cannot Prove "When"',
            description: 'Auditors ask: "When did you enable MFA?" Screenshots do not have timestamps. Excel version history is insufficient. No tamper-proof audit trail.',
            impact: 'high',
        },
        {
            title: 'Vendor Risk Management',
            description: 'Track 100+ SaaS vendors, their SOC 2 expiration dates, and security questionnaires. Manual spreadsheets miss expirations. No automated renewal alerts.',
            impact: 'medium',
        },
        {
            title: 'Continuous Compliance vs Point-in-Time',
            description: 'Annual audits create compliance drift. Infrastructure changes daily (CI/CD deployments). Cannot prove continuous adherence to controls between audits.',
            impact: 'medium',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'Compliance-as-a-Service (Vanta, Drata)',
            examples: ['Vanta', 'Drata', 'Secureframe'],
            pros: ['UI-focused', 'Screenshot automation', 'Audit management', 'Integrates with 50+ tools'],
            cons: ['Not developer-first', 'Evidence is mutable', 'No cryptographic proof', 'Expensive ($15K-40K/year)'],
            typicalCost: '$15K-40K/year',
        },
        {
            category: 'GRC Platforms (ServiceNow, Archer)',
            examples: ['ServiceNow GRC', 'Archer', 'OneTrust'],
            pros: ['Enterprise workflows', 'Risk registers', 'Audit trails', 'Policy management'],
            cons: ['Generalized (not SaaS-specific)', 'Expensive ($100K+/year)', '6-12 month implementations', 'Not API-driven'],
            typicalCost: '$100K-300K/year',
        },
        {
            category: 'Manual Audits (Big 4, boutique firms)',
            examples: ['Deloitte', 'KPMG', 'Schellman', 'A-LIGN'],
            pros: ['Full-service', 'Industry credibility', 'Personalized'],
            cons: ['Slow (4-6 months)', 'Expensive ($50K-150K)', 'Manual evidence collection', 'Annual cycles only'],
            typicalCost: '$50K-150K/audit',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Developer-first API: Immutable snapshots, not screenshots',
            'Cryptographic proof: SHA-256 hashing for tamper-evidence',
            '5-minute quickstart vs 2-week onboarding',
            'Version control for compliance: Prove "when" a control existed',
            'Cost-effective: $2K-8K/month vs $15K-40K/year platforms',
        ],
        tradeoffs: [
            'Requires coding (not a no-code platform)',
            'Self-service model (less hand-holding than consultants)',
            'Works best with cloud-native, API-accessible infrastructure',
        ],
        notFor: [
            'Non-technical compliance teams without engineering support',
            'Organizations preferring full-service consulting',
            'Legacy on-premise infrastructure without APIs',
        ],
    } as ApproachComparison,
};


export const technologyApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/technology/config-snapshots',
        description: 'Create an immutable snapshot of infrastructure configuration',
        category: 'Configuration Management',
        requiresAuth: true,
        requestExample: `curl -X POST https://api.regengine.co/v1/technology/config-snapshots \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "service": "AWS_IAM",
    "config_type": "SECURITY_POLICY",
    "config_data": {
      "account_id": "123456789012",
      "policies": [
        {
          "name": "AdminRequiresMFA",
          "mfa_enabled": true,
          "ip_restrictions": true
        }
      ],
      "users_count": 42,
      "roles_count": 18
    },
    "control_mapping": ["SOC2_CC6.1", "ISO27001_A.9.2.1"],
    "timestamp": "2024-01-26T10:00:00Z"
  }'`,
        responseExample: `{
  "snapshot_id": "cfg_0193f8a7b2c4d5e6",
  "service": "AWS_IAM",
  "content_hash": "sha256:a3f5b8c9d2e1f4a7...",
  "sealed": true,
  "created_at": "2024-01-26T10:00:01Z",
  "drift_baseline": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/technology/config-snapshots/:id',
        description: 'Retrieve a specific configuration snapshot by ID',
        category: 'Configuration Management',
        requiresAuth: true,
        responseExample: `{
  "snapshot_id": "cfg_0193f8a7b2c4d5e6",
  "service": "AWS_IAM",
  "config_type": "SECURITY_POLICY",
  "content_hash": "sha256:a3f5b8c9d2e1f4a7...",
  "sealed": true,
  "created_at": "2024-01-26T10:00:01Z",
  "drift_baseline": true
}`,
    },
    {
        method: 'POST',
        path: '/v1/technology/drift-detection',
        description: 'Detect configuration drift from baseline snapshots',
        category: 'Drift Detection',
        requiresAuth: true,
        requestExample: `{
  "baseline_snapshot_id": "cfg_0193f8a7b2c4d5e6",
  "current_config": {
    "service": "AWS_IAM",
    "config_data": { /* current config */ }
  }
}`,
        responseExample: `{
  "drift_id": "drift_0193f8a7b2c4d5e6",
  "has_drift": true,
  "drift_severity": "MEDIUM",
  "changes": [
    {
      "field": "policies[0].mfa_enabled",
      "baseline_value": true,
      "current_value": false,
      "risk_level": "HIGH"
    }
  ],
  "total_changes": 1,
  "detected_at": "2024-01-26T10:05:00Z"
}`,
    },
    {
        method: 'GET',
        path: '/v1/technology/vendor-tracking',
        description: 'Track SaaS vendor security certifications and expiration dates',
        category: 'Vendor Management',
        requiresAuth: true,
        responseExample: `{
  "vendors": [
    {
      "vendor_id": "vnd_github",
      "name": "GitHub",
      "soc2_status": "ACTIVE",
      "soc2_expiration": "2024-12-31",
      "iso27001_certified": true,
      "risk_score": 12
    },
    {
      "vendor_id": "vnd_datadog",
      "name": "Datadog",
      "soc2_status": "EXPIRING_SOON",
      "soc2_expiration": "2024-02-15",
      "iso27001_certified": true,
      "risk_score": 25
    }
  ],
  "total": 2,
  "expiring_within_90_days": 1
}`,
    },
    {
        method: 'POST',
        path: '/v1/technology/audit-export',
        description: 'Export SOC 2 or ISO 27001 audit evidence package',
        category: 'Audit & Reporting',
        requiresAuth: true,
        requestExample: `{
  "audit_standard": "SOC2_TYPE_II",
  "audit_period_start": "2024-01-01",
  "audit_period_end": "2024-12-31",
  "controls": ["CC6.1", "CC6.6", "CC7.2"],
  "format": "ZIP"
}`,
        responseExample: `{
  "export_id": "exp_0193f8a7b2c4d5e6",
  "status": "GENERATING",
  "download_url": null,
  "snapshot_count": 1247,
  "estimated_completion": "2024-01-26T10:20:00Z"
}`,
    },
    {
        method: 'GET',
        path: '/v1/technology/iso-27001-control-status',
        description: 'Get ISO 27001 Annex A control implementation status',
        category: 'ISO Compliance',
        requiresAuth: true,
        responseExample: `{
  "standard": "ISO/IEC 27001:2022",
  "overall_compliance": 78,
  "annex_a_controls": {
    "implemented": 72,
    "partial": 14,
    "not_implemented": 7,
    "total": 93
  },
  "key_gaps": [
    {"control": "A.8.8", "name": "Management of technical vulnerabilities", "status": "PARTIAL"},
    {"control": "A.8.23", "name": "Web filtering", "status": "NOT_IMPLEMENTED"}
  ],
  "certification_estimate": "6_TO_9_MONTHS"
}`,
    },
    {
        method: 'POST',
        path: '/v1/technology/iso-20000-incident-tracking',
        description: 'Track ISO 20000 IT service incidents and resolution times',
        category: 'ISO Compliance',
        requiresAuth: true,
        requestExample: `{
  "incident_id": "INC-2024-001234",
  "service": "SaaS Platform",
  "priority": "P2",
  "category": "AVAILABILITY",
  "reported_at": "2024-01-26T10:00:00Z",
  "resolved_at": "2024-01-26T12:30:00Z",
  "resolution_time_minutes": 150,
  "sla_target_minutes": 240
}`,
        responseExample: `{
  "tracking_id": "iso20000_0193f8a7b2c4d5e6",
  "incident_id": "INC-2024-001234",
  "sla_met": true,
  "resolution_time_minutes": 150,
  "sla_compliance_percentage": 95.2,
  "trend": "IMPROVING"
}`,
    },
];

export const technologySdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/technology-sdk',
        description: 'Type-safe SDK for SaaS compliance automation',
        quickstartCode: `import { TechnologyCompliance } from '@regengine/technology-sdk';

const tech = new TechnologyCompliance('rge_your_api_key');

// Snapshot AWS IAM configuration
const snapshot = await tech.configSnapshots.create({
  service: 'AWS_IAM',
  config_type: 'SECURITY_POLICY',
  config_data: {
    account_id: '123456789012',
    policies: [{
      name: 'AdminRequiresMFA',
      mfa_enabled: true
    }]
  },
  control_mapping: ['SOC2_CC6.1', 'ISO27001_A.9.2.1']
});

console.log('✅ Config snapshot created:', snapshot.snapshot_id);
console.log('🔒 Content hash:', snapshot.content_hash);
console.log('📊 Drift baseline:', snapshot.drift_baseline);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-technology',
        description: 'Python SDK for infrastructure compliance',
        quickstartCode: `from regengine.technology import TechnologyCompliance

tech = TechnologyCompliance(api_key='rge_your_api_key')

# Snapshot AWS IAM configuration
snapshot = tech.config_snapshots.create(
    service='AWS_IAM',
    config_type='SECURITY_POLICY',
    config_data={
        'account_id': '123456789012',
        'policies': [{
            'name': 'AdminRequiresMFA',
            'mfa_enabled': True
        }]
    },
    control_mapping=['SOC2_CC6.1', 'ISO27001_A.9.2.1']
)

print(f'✅ Config snapshot: {snapshot.snapshot_id}')
print(f'🔒 Content hash: {snapshot.content_hash}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/technology-sdk-go',
        description: 'Go SDK for high-performance compliance automation',
        quickstartCode: `package main

import (
    "github.com/regengine/technology-sdk-go"
)

func main() {
    client := technology.NewClient("rge_your_api_key")
    
    snapshot, err := client.ConfigSnapshots.Create(&technology.ConfigRequest{
        Service: "AWS_IAM",
        ConfigType: "SECURITY_POLICY",
        ControlMapping: []string{"SOC2_CC6.1", "ISO27001_A.9.2.1"},
    })
    
    if err != nil {
        panic(err)
    }
    
    fmt.Printf("Snapshot: %s\\n", snapshot.ID)
}`,
    },
];
