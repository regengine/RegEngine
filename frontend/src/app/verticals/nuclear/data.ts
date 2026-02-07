import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const nuclearIndustryData = {
    industry: 'Nuclear',
    description: `Nuclear power plants operate under the most stringent regulatory framework in the world. 10 CFR 50 Appendix B requires comprehensive quality assurance records that must be preserved for the facility's entire lifecycle—often 60+ years. The Nuclear Regulatory Commission (NRC) conducts rigorous inspections with zero tolerance for documentation gaps. A single compliance failure can trigger enforcement actions, $100K+ daily fines, or operating license review affecting a $1B+ annual revenue plant.`,

    regulations: [
        {
            name: '10 CFR 50 Appendix B',
            shortName: '10 CFR 50 App B',
            description:
                'Quality Assurance Criteria for Nuclear Power Plants. Requires comprehensive QA programs with immutable record-keeping for all safety-related activities.',
            authority: 'U.S. Nuclear Regulatory Commission (NRC)',
        },
        {
            name: '10 CFR 73',
            shortName: '10 CFR 73',
            description:
                'Physical Protection of Plants and Materials. Mandates cyber security plans, access controls, and incident response for critical digital assets.',
            authority: 'U.S. Nuclear Regulatory Commission (NRC)',
        },
        {
            name: '10 CFR 21',
            shortName: '10 CFR 21',
            description:
                'Reporting of Defects and Noncompliance. Requires immediate reporting of substantial safety hazards and preservation of evidence.',
            authority: 'U.S. Nuclear Regulatory Commission (NRC)',
        },
        {
            name: 'NUREG-0800 (Standard Review Plan)',
            shortName: 'SRP',
            description:
                'Guidance for reviewing license applications. Defines acceptable methods for demonstrating compliance with NRC regulations.',
            authority: 'U.S. Nuclear Regulatory Commission (NRC)',
        },
        {
            name: 'ISO 19443:2018',
            shortName: 'ISO 19443',
            description:
                'Quality Management Systems - Specific requirements for the application of ISO 9001 in the nuclear sector. Addresses nuclear-specific quality requirements including safety culture, counterfeit parts prevention, and configuration management throughout facility lifecycle. ~5,000 certifications worldwide.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 9001:2015',
            shortName: 'ISO 9001',
            description:
                'Quality Management Systems - Requirements. Foundation standard for nuclear quality programs. ISO 19443 extends ISO 9001 with nuclearspecific requirements. Provides framework for process control, document management, and continuous improvement.',
            authority: 'International Organization for Standardization (ISO)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'Absolute Immutability Requirements',
            description:
                'Records cannot be altered, deleted, or modified—ever. Traditional databases allow UPDATE and DELETE operations. A single mutable record can invalidate an entire audit.',
            impact: 'high',
        },
        {
            title: 'Chain of Custody Verification',
            description:
                'Must cryptographically prove document lineage from creation through 60+ years. Paper trails are insufficient. Requires tamper-evident digital signatures.',
            impact: 'high',
        },
        {
            title: '60+ Year Retention with Technology Migration',
            description:
                'Records must survive multiple technology migrations (tape → disk → cloud). Legacy systems break, formats become obsolete. Must ensure forward compatibility.',
            impact: 'high',
        },
        {
            title: 'Legal Discovery Under Time Pressure',
            description:
                'NRC enforcement actions require evidence export within 24-48 hours. Manual searching through decades of records is infeasible.',
            impact: 'medium',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'Electronic Document Management Systems (EDMS)',
            examples: ['SharePoint', 'Documentum', 'IBM FileNet'],
            pros: ['Familiar enterprise tools', 'Searchable metadata', 'Workflow automation'],
            cons: [
                'Mutable by design (admin can delete/edit)',
                'No cryptographic verification',
                'Audit logs can be tampered',
                'Not designed for 60+ year retention',
            ],
            typicalCost: '$100K-300K/year',
        },
        {
            category: 'Blockchain/DLT Vendors',
            examples: ['IBM Blockchain', 'R3 Corda', 'Hyperledger'],
            pros: ['Immutability guarantee', 'Distributed consensus', 'Cryptographic proof'],
            cons: [
                'Overly complex for single-entity use',
                'Expensive ($500K+ implementations)',
                'Slow transaction speeds',
                'Requires blockchain expertise',
            ],
            typicalCost: '$500K-2M (implementation)',
        },
        {
            category: 'Paper Archives with Offsite Storage',
            examples: ['Iron Mountain', 'Access Corporation'],
            pros: ['NRC-compliant', 'Physical tamper-evidence', 'Proven longevity'],
            cons: [
                'Unsearchable',
                'Disaster-vulnerable (fire, flood)',
                'Slow retrieval (days, not minutes)',
                'Cannot verify integrity remotely',
            ],
            typicalCost: '$50K-200K/year',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Database-enforced immutability: PostgreSQL constraints prevent UPDATEs/DELETEs',
            'Cryptographic hashing: SHA-256 content verification',
            'Legal discovery export: Minutes, not weeks',
            'API-driven integration: Works with existing systems',
            'Cost-effective: $5K-15K/month vs $500K+ blockchain implementations',
        ],
        tradeoffs: [
            'Requires PostgreSQL 14+ (some plants run legacy Oracle)',
            'Self-managed or cloud-hosted (not on-premise air-gapped by default)',
            'Developer integration required (not point-and-click)',
        ],
        notFor: [
            'Plants without modern infrastructure or API access',
            'Organizations requiring 100% on-premise air-gapped solutions',
            'Teams without technical implementation resources',
        ],
    } as ApproachComparison,
};

export const nuclearApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/nuclear/records',
        description: 'Create an immutable, sealed record for nuclear compliance documentation',
        category: 'Records',
        requiresAuth: true,
        requestExample: `curl -X POST https://api.regengine.co/v1/nuclear/records \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "docketNumber": "50-12345",
    "facilityId": "NPP-UNIT-1",
    "recordType": "CYBER_SECURITY_PLAN",
    "document": {
      "title": "CY2024 Cyber Security Implementation Plan",
      "version": "2.1",
      "author": "John Smith, CISSP",
      "classification": "SAFEGUARDS_INFORMATION"
    },
    "regulatory": {
      "cfr": "10 CFR 73.54",
      "inspectionReady": true
    }
  }'`,
        responseExample: `{
  "id": "rec_0193f8a7b2c4d5e6",
  "docketNumber": "50-12345",
  "contentHash": "sha256:a3f5b8c9d2e1f4a7...",
  "integrity": {
    "sealed": true,
    "chainStatus": "valid",
    "previousHash": "sha256:b8c9d2e1f4a7b3f5..."
  },
  "createdAt": "2024-01-26T10:00:05Z",
  "immutable": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/nuclear/records/:id',
        description: 'Retrieve a specific record by ID with full integrity verification',
        category: 'Records',
        requiresAuth: true,
        responseExample: `{
  "id": "rec_0193f8a7b2c4d5e6",
  "docketNumber": "50-12345",
  "facilityId": "NPP-UNIT-1",
  "recordType": "CYBER_SECURITY_PLAN",
  "contentHash": "sha256:a3f5b8c9d2e1f4a7...",
  "sealed": true,
  "createdAt": "2024-01-26T10:00:05Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/nuclear/records/:id/verify',
        description: 'Cryptographically verify record integrity and chain-of-custody',
        category: 'Verification',
        requiresAuth: true,
        responseExample: `{
  "recordId": "rec_0193f8a7b2c4d5e6",
  "isValid": true,
  "chainValid": true,
  "verificationMethod": "sha256",
  "chainDepth": 1247,
  "verifiedAt": "2024-01-26T10:05:00Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/nuclear/legal-hold',
        description: 'Place records under legal hold for NRC enforcement actions or discovery',
        category: 'Legal Hold',
        requiresAuth: true,
        requestExample: `{
  "recordIds": ["rec_0193f8a7b2c4d5e6", "rec_0193f8a7b2c4d5e7"],
  "reason": "NRC Enforcement Action EA-24-001",
  "expiresAt": "2025-01-26T00:00:00Z"
}`,
        responseExample: `{
  "holdId": "hold_0193f8a7b2c4d5e8",
  "recordCount": 2,
  "status": "ACTIVE",
  "createdAt": "2024-01-26T10:10:00Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/nuclear/export',
        description: 'Export records for NRC discovery with cryptographic proof bundle',
        category: 'Export',
        requiresAuth: true,
        requestExample: `{
  "recordIds": ["rec_0193f8a7b2c4d5e6"],
  "format": "PDF_WITH_SIGNATURES",
  "includeChainProof": true
}`,
        responseExample: `{
  "exportId": "exp_0193f8a7b2c4d5e9",
  "downloadUrl": "https://api.regengine.co/downloads/exp_0193...",
  "expiresAt": "2024-01-27T10:15:00Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/nuclear/iso-19443-quality-assurance',
        description: 'Track ISO 19443 nuclear quality assurance events and non-conformances',
        category: 'ISO Compliance',
        requiresAuth: true,
        requestExample: `{
  "facility_id": "NPP-UNIT-1",
  "event_type": "NON_CONFORMANCE",
  "description": "Welding procedure deviated from qualified specification",
  "safety_significance": "SAFETY_RELATED",
  "corrective_action_required": true,
  "parts_traceability_verified": true,
  "technical_specification_impact": false
}`,
        responseExample: `{
  "qa_id": "iso19443_0193f8a7b2c4d5e6",
  "facility_id": "NPP-UNIT-1",
  "root_cause_analysis_required": true,
  "nrc_reportable": false,
  "corrective_action_status": "IN_PROGRESS",
  "quality_level": "SAFETY_RELATED",
  "configuration_management_updated": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/nuclear/iso-9001-capa-metrics',
        description: 'Get ISO 9001 Corrective and Preventive Action (CAPA) metrics',
        category: 'ISO Compliance',
        requiresAuth: true,
        responseExample: `{
  "standard": "ISO 9001:2015",
  "facility_id": "NPP-UNIT-1",
  "capa_performance": {
    "open_capas": 12,
    "overdue_capas": 2,
    "avg_closure_time_days": 45,
    "repeat_issues": 1
  },
  "quality_trends": {
    "total_non_conformances_ytd": 78,
    "safety_related": 12,
    "trend": "DECREASING"
  },
  "audit_findings_open": 5,
  "management_review_due": "2024-03-15"
}`,
    },
];

export const nuclearSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/nuclear-sdk',
        description: 'Type-safe SDK for Node.js and TypeScript applications',
        quickstartCode: `import { NuclearCompliance } from '@regengine/nuclear-sdk';

const nuclear = new NuclearCompliance('rge_your_api_key');

// Create immutable record
const record = await nuclear.records.create({
  docketNumber: '50-12345',
  facilityId: 'NPP-UNIT-1',
  recordType: 'CYBER_SECURITY_PLAN',
  document: {
    title: 'CY2024 Cyber Security Plan',
    version: '2.1'
  }
});

console.log('Record created:', record.id);
console.log('Sealed:', record.integrity.sealed);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-nuclear',
        description: 'Python SDK for automation and integration',
        quickstartCode: `from regengine.nuclear import NuclearCompliance

nuclear = NuclearCompliance(api_key='rge_your_api_key')

# Create immutable record
record = nuclear.records.create(
    docket_number='50-12345',
    facility_id='NPP-UNIT-1',
    record_type='CYBER_SECURITY_PLAN',
    document={
        'title': 'CY2024 Cyber Security Plan',
        'version': '2.1'
    }
)

print(f'Record: {record.id}')
print(f'Sealed: {record.integrity.sealed}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/nuclear-sdk-go',
        description: 'Go SDK for high-performance applications',
        quickstartCode: `package main

import (
    "github.com/regengine/nuclear-sdk-go"
)

func main() {
    client := nuclear.NewClient("rge_your_api_key")
    
    record, err := client.Records.Create(&nuclear.RecordRequest{
        DocketNumber: "50-12345",
        FacilityID:   "NPP-UNIT-1",
    })
    
    fmt.Printf("Record: %s\\n", record.ID)
}`,
    },
];
