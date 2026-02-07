import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const energyIndustryData = {
    industry: 'Energy',
    description: `The energy sector faces unprecedented cybersecurity challenges. With 3,000+ utilities managing critical infrastructure serving 334 million people, bulk electric systems are prime targets for nation-state actors and ransomware groups. NERC CIP-013-1 mandates supply chain cyber security risk management—but compliance is complex, expensive, and often reactive. A single compliance failure can result in $1M+ daily fines and potential grid instability affecting millions.`,

    regulations: [
        {
            name: 'NERC CIP-013-1',
            shortName: 'CIP-013',
            description:
                'Cyber Security - Supply Chain Risk Management. Requires utilities to implement risk management plans for vendors and supply chain partners with access to critical cyber assets.',
            authority: 'North American Electric Reliability Corporation (NERC)',
        },
        {
            name: 'NERC CIP-010-4',
            shortName: 'CIP-010',
            description:
                'Configuration Change Management and Vulnerability Assessments. Mandates baseline configurations and monitoring of all changes to critical cyber assets.',
            authority: 'North American Electric Reliability Corporation (NERC)',
        },
        {
            name: 'NERC CIP-007-6',
            shortName: 'CIP-007',
            description:
                'System Security Management. Requires patch management, security event monitoring, and malware prevention for all critical infrastructure.',
            authority: 'North American Electric Reliability Corporation (NERC)',
        },
        {
            name: 'FERC Order 887',
            shortName: 'FERC 887',
            description:
                'Enhanced cybersecurity standards for the bulk power system, including incident response and recovery requirements.',
            authority: 'Federal Energy Regulatory Commission (FERC)',
        },
        {
            name: 'ISO 50001:2018',
            shortName: 'ISO 50001',
            description:
                'Energy Management Systems - Requirements with guidance for use. Enables systematic approach to continually improving energy performance. Typical energy cost reductions of 10-30% achievable. ~50,000 certifications worldwide.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 55001:2014',
            shortName: 'ISO 55001',
            description:
                'Asset Management - Management Systems - Requirements. Enables utilities to optimize asset lifecycle, reduce unplanned downtime, and demonstrate efficient asset management to regulators. Critical for infrastructure reliability.',
            authority: 'International Organization for Standardization (ISO)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'Manual Documentation Overload',
            description:
                'Utilities track 100+ vendors across spreadsheets. No centralized system of record. Auditors request evidence that takes weeks to compile manually.',
            impact: 'high',
        },
        {
            title: 'No Cryptographic Audit Trail',
            description:
                'Cannot prove "when" a configuration existed. Excel files are mutable. NERC auditors require timestamped, tamper-proof evidence of compliance actions.',
            impact: 'high',
        },
        {
            title: 'Expensive Consultant Dependencies',
            description:
                '$200K+ annual retainers for paper-based tracking. 6-8 week audit cycles. Manual screenshot collection. Consultants become single point of failure.',
            impact: 'medium',
        },
        {
            title: 'Legacy SCADA System Constraints',
            description:
                'ICS/SCADA systems with limited API capabilities. Air-gapped networks. Requires manual intervention for change documentation.',
            impact: 'medium',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'Traditional Compliance Consultants',
            examples: ['Big 4 Firms', 'Specialized Energy Consultants'],
            pros: [
                'Deep NERC expertise',
                'Established audit relationships',
                'Full-service compliance management',
            ],
            cons: [
                'Manual processes (6-8 week cycles)',
                'Extremely expensive ($150-300/hr, $200K+ annually)',
                'No real-time visibility',
                'Paper-based evidence collection',
            ],
            typicalCost: '$200K-500K/year',
        },
        {
            category: 'GRC Platforms',
            examples: ['ServiceNow GRC', 'Archer', 'LogicGate'],
            pros: ['Workflow automation', 'Audit trail', 'Centralized controls'],
            cons: [
                'Not energy-specific',
                'Poor supply chain integration',
                'No cryptographic verification',
                'Expensive implementation (6-12 months)',
            ],
            typicalCost: '$50K-150K/year',
        },
        {
            category: 'DIY Spreadsheets',
            examples: ['Excel', 'Google Sheets', 'SharePoint'],
            pros: ['Free or low-cost', 'Familiar to teams', 'Flexible'],
            cons: [
                'Unmaintainable at scale',
                'No audit trail',
                'Error-prone',
                'Cannot prove integrity',
            ],
            typicalCost: '$0-5K/year',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'API-first architecture: 5-minute quickstart vs 6-week onboarding',
            'Cryptographic snapshots: Immutable, timestamped evidence',
            'Developer-friendly: Type-safe SDKs for Node.js, Python, Go',
            'Cost-effective: Starting at $2,500/month vs $200K+ consultants',
            'Real-time compliance monitoring',
        ],
        tradeoffs: [
            'Requires developer integration (not a no-code solution)',
            'Works best with modern APIs (may need middleware for legacy SCADA)',
            'Self-service model (less hand-holding than consultants)',
        ],
        notFor: [
            'Utilities without API capabilities or technical staff',
            'Organizations requiring full-service consulting',
            'Air-gapped environments with zero external connectivity',
        ],
    } as ApproachComparison,
};

export const energyApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/energy/snapshots',
        description: 'Create an immutable compliance snapshot for a substation or facility',
        category: 'Snapshots',
        requiresAuth: true,

        requestExample: `curl -X POST https://api.regengine.co/v1/energy/snapshots \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "substationId": "ALPHA-001",
    "facilityName": "Alpha Substation",
    "systemStatus": "NOMINAL",
    "assets": [
      {
        "id": "T1",
        "type": "TRANSFORMER",
        "firmwareVersion": "2.4.1",
        "lastVerified": "2024-01-26T10:00:00Z"
      }
    ],
    "espConfig": {
      "firewallVersion": "2.4.1",
      "idsEnabled": true,
      "patchLevel": "current"
    },
    "regulatory": {
      "standard": "NERC-CIP-013-1",
      "auditReady": true
    }
  }'`,
        responseExample: `{
  "id": "snap_0193f8a7b2c4d5e6",
  "substationId": "ALPHA-001",
  "contentHash": "sha256:a3f5b8c9d2e1f4a7...",
  "chainStatus": "valid",
  "previousHash": "sha256:b8c9d2e1f4a7b3f5...",
  "createdAt": "2024-01-26T10:00:05Z",
  "sealed": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/energy/snapshots/:id',
        description: 'Retrieve a specific snapshot by ID',
        category: 'Snapshots',
        requiresAuth: true,
        responseExample: `{
  "id": "snap_0193f8a7b2c4d5e6",
  "substationId": "ALPHA-001",
  "facilityName": "Alpha Substation",
  "systemStatus": "NOMINAL",
  "contentHash": "sha256:a3f5b8c9d2e1f4a7...",
  "chainStatus": "valid",
  "sealed": true,
  "createdAt": "2024-01-26T10:00:05Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/energy/snapshots/:id/verify',
        description: 'Cryptographically verify snapshot integrity and chain validity',
        category: 'Verification',
        requiresAuth: true,
        responseExample: `{
  "snapshotId": "snap_0193f8a7b2c4d5e6",
  "isValid": true,
  "chainValid": true,
  "verificationMethod": "sha256",
  "verifiedAt": "2024-01-26T10:05:00Z"
}`,
    },
    {
        method: 'GET',
        path: '/v1/energy/facilities',
        description: 'List all registered facilities/substations',
        category: 'Facilities',
        requiresAuth: true,
        responseExample: `{
  "facilities": [
    {
      "id": "ALPHA-001",
      "name": "Alpha Substation",
      "location": "Sacramento, CA",
      "snapshotCount": 42
    }
  ],
  "total": 1
}`,
    },
    {
        method: 'POST',
        path: '/v1/energy/incidents',
        description: 'Trigger an incident snapshot from security events',
        category: 'Incidents',
        requiresAuth: true,
        requestExample: `{
  "substationId": "ALPHA-001",
  "incidentType": "UNAUTHORIZED_ACCESS",
  "severity": "HIGH",
  "description": "Suspicious login attempt detected"
}`,
        responseExample: `{
  "incidentId": "inc_0193f8a7b2c4d5e6",
  "snapshotId": "snap_0193f8a7b2c4d5e7",
  "status": "RECORDED",
  "createdAt": "2024-01-26T10:10:00Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/energy/iso-50001-certification',
        description: 'Track ISO 50001 energy management certification status and surveillance audits',
        category: 'ISO Compliance',
        requiresAuth: true,
        requestExample: `{
  "facility_id": "ALPHA-001",
  "certification_body": "BSI",
  "certificate_number": "EM-123456",
  "issue_date": "2024-01-15",
  "expiry_date": "2027-01-15",
  "scope": "Energy management for 138kV substation",
  "energy_performance_improvement": 15.3,
  "baseline_year": 2023
}`,
        responseExample: `{
  "cert_id": "iso50001_0193f8a7b2c4d5e6",
  "facility_id": "ALPHA-001",
  "standard": "ISO 50001:2018",
  "status": "ACTIVE",
  "next_surveillance": "2025-01-15",
  "certification_level": "FULL",
  "energy_savings_validated": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/energy/iso-55001-gap-analysis',
        description: 'Automated gap analysis against ISO 55001 asset management requirements',
        category: 'ISO Compliance',
        requiresAuth: true,
        requestExample: `?facility_id=ALPHA-001`,
        responseExample: `{
  "facility_id": "ALPHA-001",
  "standard": "ISO 55001:2014",
  "overall_readiness": 73,
  "gaps": [
    {
      "clause": "4.3",
      "requirement": "Determining the scope of asset management system",
      "status": "PARTIAL",
      "recommendation": "Document asset portfolio boundaries more explicitly"
    },
    {
      "clause": "6.2.2",
      "requirement": "Asset management objectives",
      "status": "MISSING",
      "recommendation": "Establish quantifiable asset performance objectives"
    }
  ],
  "compliant_clauses": 15,
  "total_clauses": 21,
  "estimated_effort_hours": 120
}`,
    },
];


export const energySdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/energy-sdk',
        description: 'Type-safe SDK for Node.js and TypeScript applications',
        quickstartCode: `import { EnergyCompliance } from '@regengine/energy-sdk';

const energy = new EnergyCompliance('rge_your_api_key');

// Create snapshot
const snapshot = await energy.snapshots.create({
  substationId: 'ALPHA-001',
  facilityName: 'Alpha Substation',
  systemStatus: 'NOMINAL',
  regulatory: {
    standard: 'NERC-CIP-013-1',
    auditReady: true
  }
});

console.log('Snapshot created:', snapshot.id);
console.log('Hash:', snapshot.contentHash);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-energy',
        description: 'Python SDK for automation and integration',
        quickstartCode: `from regengine.energy import EnergyCompliance

energy = EnergyCompliance(api_key='rge_your_api_key')

# Create snapshot
snapshot = energy.snapshots.create(
    substation_id='ALPHA-001',
    facility_name='Alpha Substation',
    system_status='NOMINAL',
    regulatory={
        'standard': 'NERC-CIP-013-1',
        'audit_ready': True
    }
)

print(f'Snapshot created: {snapshot.id}')
print(f'Hash: {snapshot.content_hash}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/energy-sdk-go',
        description: 'Go SDK for high-performance applications',
        quickstartCode: `package main

import (
    "github.com/regengine/energy-sdk-go"
)

func main() {
    client := energy.NewClient("rge_your_api_key")
    
    snapshot, err := client.Snapshots.Create(&energy.SnapshotRequest{
        SubstationID: "ALPHA-001",
        FacilityName: "Alpha Substation",
        SystemStatus: "NOMINAL",
    })
    
    fmt.Printf("Snapshot: %s\\n", snapshot.ID)
}`,
    },
];
