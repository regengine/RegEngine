import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const aerospaceIndustryData = {
    industry: 'Aerospace',
    description: `The aerospace industry operates under the most stringent quality and safety standards globally. AS9100 (aerospace quality management built on ISO 9001) governs 25,000+ certified suppliers worldwide, serving commercial aviation (Boeing, Airbus), defense contractors (Lockheed Martin, Northrop Grumman), and space agencies (NASA, ESA). A single defect can result in catastrophic failure, aircraft groundings, and multi-billion dollar recalls. First Article Inspection (FAI) per AS9102 requires dimensional verification of every unique configuration. Configuration management is life-critical—unapproved changes can compromise flight safety. Compliance costs for Tier 1 suppliers: $200K-500K annually. Aerospace parts have cradle-to-grave traceability requirements spanning 30+ year lifecycles.`,

    regulations: [
        {
            name: 'AS9100D',
            shortName: 'AS9100',
            description:
                'Aerospace Quality Management Systems - Requirements for Aviation, Space, and Defense. Built on ISO 9001 with aerospace-specific requirements: configuration management, product safety, counterfeit part prevention, key characteristics control. 25,000+ certified organizations globally.',
            authority: 'International Aerospace Quality Group (IAQG)',
        },
        {
            name: 'AS9102B',
            shortName: 'AS9102',
            description:
                'First Article Inspection (FAI) Requirement. Mandates dimensional verification, material certification, and functional testing for every unique part/assembly configuration. FAI reports required before production. Non-compliance = shipment rejection.',
            authority: 'SAE International',
        },
        {
            name: 'AS9145A',
            shortName: 'AS9145',
            description:
                'Configuration Management for Aerospace Products. Requires comprehensive change control, version tracking, and approval workflows. Unauthorized configuration changes can result in airworthiness certificate suspension.',
            authority: 'SAE International',
        },
        {
            name: 'NADCAP',
            shortName: 'NADCAP',
            description:
                'National Aerospace and Defense Contractors Accreditation Program. Special process accreditation (heat treat, welding, coating, NDT). Required by Boeing, Airbus, Lockheed, Raytheon. Re-audits every 6-24 months at $20K-50K per process.',
            authority: 'Performance Review Institute (PRI)',
        },
        {
            name: 'FAA Part 145',
            shortName: 'Part 145',
            description:
                'Repair Station Certification. Required for aircraft maintenance, preventive maintenance, or alterations. Rigorous documentation and traceability mandates. Random FAA audits with zero tolerance for non-compliance.',
            authority: 'Federal Aviation Administration (FAA)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'First Article Inspection (FAI) Bottlenecks',
            description:
                'AS9102 requires dimensional inspection for every configuration. FAI reports are 20-50 pages with measurement data, certifications, and signatures. Manual compilation takes 40-80 hours. Errors cause customer rejection.',
            impact: 'high',
        },
        {
            title: 'Configuration Management Failures',
            description:
                'Engineering changes must be traceable across part lifecycle (30+ years for aircraft). Paper-based systems lose revision history. Cannot prove what configuration was delivered to which aircraft. Airworthiness risk.',
            impact: 'high',
        },
        {
            title: 'NADCAP Audit Nightmares',
            description:
                'Special process audits require evidence of every heat lot, weld parameter, and coating thickness. Missing pyrometry data = automatic failure. Re-audit costs $30K+. Customer production delays.',
            impact: 'medium',
        },
        {
            title: 'Counterfeit Part Prevention',
            description:
                'AS9100 clause 8.1.4 mandates counterfeit prevention. Salvage/surplus parts infiltrate supply chains. No cryptographic verification of supplier certifications. Risk of fraudulent MTC (Material Test Certificates).',
            impact: 'high',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'Aerospace QMS Platforms',
            examples: ['ETQ Reliance', 'Agile PLM', 'SAP Aerospace \u0026 Defense'],
            pros: [
                'AS9100 workflow templates',
                'FAI form generation',
                'Configuration management',
                'NADCAP audit tracking',
            ],
            cons: [
                'Extremely expensive ($200K-1M+ implementation)',
                'Long deployment (18-36 months)',
                'No cryptographic verification',
                'Poor multi-site integration',
            ],
            typicalCost: '$150K-500K/year',
        },
        {
            category: 'Certification Bodies',
            examples: ['PRI (NADCAP)', 'SAI Global', 'NQA', 'Intertek'],
            pros: [
                'AS9100 certification authority',
                'NADCAP accreditation',
                'Aerospace expertise',
            ],
            cons: [
                'No technology platform',
                'Manual audit prep (8-12 weeks)',
                'Expensive ($40K-100K per cycle)',
                'Reactive audits, not preventive monitoring',
            ],
            typicalCost: '$100K-200K/year',
        },
        {
            category: 'DIY / Manual Systems',
            examples: ['Excel FAI forms', 'PDF travelers', 'Paper logbooks'],
            pros: ['Low initial cost', 'Familiar to engineers'],
            cons: [
                'Cannot prove data integrity',
                'Customer rejects FAI reports',
                'Configuration change errors',
                'Audit failures',
            ],
            typicalCost: '$20K-50K/year (labor)',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Cryptographic FAI reports: Immutable AS9102 Form 3 with measurement data',
            'Configuration baselines: SHA-256 fingerprints for part revisions',
            'NADCAP evidence vault: Timestamped pyrometry, MTR, CMM data',
            'Counterfeit prevention: Blockchain-anchored supplier certifications',
            'Starting at $8,500/month vs $300K+/year for Tier 1 aerospace suppliers',
        ],
        tradeoffs: [
            'Requires PLM/ERP integration (not a standalone QMS)',
            'Best for Tier 1/2 suppliers with API capabilities',
            'Still need AS9100 auditors and NADCAP accreditation (we provide evidence, not certification)',
        ],
        notFor: [
            'Tier 3 machine shops without technical resources',
            'Companies requiring full consulting services',
            'Organizations seeking certification body services',
        ],
    } as ApproachComparison,
};

export const aerospaceApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/aerospace/fai',
        description: 'Create immutable First Article Inspection (FAI) report per AS9102 with cryptographic verification',
        category: 'FAI',
        requiresAuth: true,

        requestExample: `curl -X POST https://api.regengine.co/v1/aerospace/fai \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "part_number": "BA-45678-REV-F",
    "customer": "Boeing",
    "configuration": "REV-F-CONFIG-01",
    "form1_data": {
      "part_name": "Wing Spar Bracket",
      "drawing_number": "BA-45678",
      "revision": "F"
    },
    "form3_measurements": [
      {
        "characteristic_number": 1,
        "characteristic": "Overall Length",
        "specification": "100.0 ± 0.2 mm",
        "actual_measurement": 100.05,
        "deviation": 0.05,
        "measuring_equipment": "CMM-001",
        "calibration_due": "2024-06-15"
      }
    ],
    "material_certs": ["MTC-2024-001", "MTC-2024-002"],
    "functional_test_results": "PASS",
    "inspector": "FAI Inspector - R. Martinez",
    "inspection_date": "2024-01-26"
  }'`,
        responseExample: `{
  "fai_id": "fai_0193f8a7b2c4d5e6",
  "part_number": "BA-45678-REV-F",
  "contentHash": "sha256:f5a8c9d4e1f4a7b3...",
  "configuration_hash": "sha256:c9d4e1f4a7b3f5a8...",
  "sealed": true,
  "as9102_compliant": true,
  "customer_portal_ready": true
}`,
    },
    {
        method: 'POST',
        path: '/v1/aerospace/config-baseline',
        description: 'Create immutable configuration baseline with SHA-256 fingerprint for part revision tracking',
        category: 'Configuration',
        requiresAuth: true,
        requestExample: `{
  "part_number": "BA-45678-REV-F",
  "revision": "F",
  "ecn_number": "ECN-2024-047",
  "change_description": "Material upgrade from 7075-T6 to 7085-T74 aluminum",
  "approved_by": "Engineering Manager - K. Thompson",
  "approval_date": "2024-01-25",
  "drawings": ["DWG-001-REV-F.pdf", "DWG-002-REV-F.pdf"],
  "specifications": ["SPEC-MAT-001", "SPEC-PROC-002"],
  "effectivity": "Serial SN-1001 and subsequent"
}`,
        responseExample: `{
  "baseline_id": "cfg_0193f8a7b2c4d5e6",
  "part_number": "BA-45678-REV-F",
  "revision": "F",
  "configurationHash": "sha256:a8c9d4e1f4a7b3f5...",
  "previous_baseline_hash": "sha256:d4e1f4a7b3f5a8c9...",
  "sealed": true,
  "chain_valid": true
}`,
    },
    {
        method: 'POST',
        path: '/v1/aerospace/nadcap-evidence',
        description: 'Record NADCAP special process evidence (heat treat, welding, coating, NDT) with cryptographic timestamp',
        category: 'NADCAP',
        requiresAuth: true,
        requestExample: `{
  "process_type": "HEAT_TREAT",
  "part_number": "BA-45678-REV-F",
  "lot_number": "HT-2024-001",
  "specification": "AMS2770K",
  "furnace_id": "FURNACE-03",
  "pyrometry_data": {
    "set_point_f": 1900,
    "actual_temp_f": 1895,
    "soak_time_hours": 4.2,
    "sat_probe_serial": "SAT-12345",
    "sat_calibration_due": "2024-03-15"
  },
  "nadcap_audit_scope": "AC7102/7",
  "operator": "Heat Treat Specialist - D. Wilson"
}`,
        responseExample: `{
  "evidence_id": "ndcp_0193f8a7b2c4d5e6",
  "process_type": "HEAT_TREAT",
  "lot_number": "HT-2024-001",
  "contentHash": "sha256:b3f5a8c9d4e1f4a7...",
  "sealed": true,
  "nadcap_compliant": true,
  "next_audit": "2025-01-26"
}`,
    },
    {
        method: 'GET',
        path: '/v1/aerospace/as9100-readiness',
        description: 'Real-time AS9100D surveillance audit readiness assessment',
        category: 'Certification',
        requiresAuth: true,
        requestExample: `?facility_id=PLANT-WA-001`,
        responseExample: `{
  "facility_id": "PLANT-WA-001",
  "overall_readiness": 94,
  "standard": "AS9100D",
  "next_surveillance": "2024-07-20",
  "gaps": [
    {
      "clause": "8.1.4",
      "requirement": "Counterfeit part prevention",
      "status": "COMPLIANT",
      "evidence_count": 47
    },
    {
      "clause": "8.5.1.2",
      "requirement": "Key characteristics control",
      "status": "MINOR_GAP",
      "recommendation": "Document statistical process control for characteristic KC-042"
    }
  ],
  "nadcap_status": "CURRENT",
  "fai_submissions_ytd": 23,
  "config_changes_tracked": 156
}`,
    },
    {
        method: 'POST',
        path: '/v1/aerospace/supplier-cert-verification',
        description: 'Verify supplier material certifications with blockchain-anchored authenticity proof',
        category: 'Counterfeit Prevention',
        requiresAuth: true,
        requestExample: `{
  "cert_number": "MTC-2024-001",
  "supplier": "Aerospace Materials Inc.",
  "material": "7085-T74 Aluminum Plate",
  "heat_lot": "HL-456789",
  "cert_hash": "sha256:provided_by_supplier",
  "po_number": "PO-2024-123"
}`,
        responseExample: `{
  "verification_id": "ver_0193f8a7b2c4d5e6",
  "cert_number": "MTC-2024-001",
  "is_authentic": true,
  "blockchain_anchor": "0x7a3f8c9d4e1f4a7b...",
  "supplier_verified": true,
  "counterfeit_risk": "LOW",
  "verification_timestamp": "2024-01-26T18:00:00Z"
}`,
    },
];

export const aerospaceSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/aerospace-sdk',
        description: 'Type-safe SDK for AS9100 and FAI compliance',
        quickstartCode: `import { AerospaceCompliance } from '@regengine/aerospace-sdk';

const aero = new AerospaceCompliance('rge_your_api_key');

// Create immutable FAI report
const fai = await aero.fai.create({
  part_number: 'BA-45678-REV-F',
  customer: 'Boeing',
  configuration: 'REV-F-CONFIG-01',
  form3_measurements: [
    {
      characteristic_number: 1,
      characteristic: 'Overall Length',
      specification: '100.0 ± 0.2 mm',
      actual_measurement: 100.05
    }
  ],
  inspector: 'FAI Inspector - R. Martinez'
});

console.log('✅ FAI sealed:', fai.fai_id);
console.log('🔒 Hash:', fai.contentHash);
console.log('📋 AS9102 compliant:', fai.as9102_compliant);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-aerospace',
        description: 'Python SDK for PLM/ERP integration',
        quickstartCode: `from regengine.aerospace import AerospaceCompliance

aero = AerospaceCompliance(api_key='rge_your_api_key')

# Create configuration baseline
baseline = aero.config.create_baseline(
    part_number='BA-45678-REV-F',
    revision='F',
    ecn_number='ECN-2024-047',
    change_description='Material upgrade',
    approved_by='Engineering Manager - K. Thompson'
)

print(f'Config baseline: {baseline.baseline_id}')
print(f'SHA-256 hash: {baseline.configuration_hash}')
print(f'Chain valid: {baseline.chain_valid}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/aerospace-sdk-go',
        description: 'Go SDK for high-security applications',
        quickstartCode: `package main

import (
    "github.com/regengine/aerospace-sdk-go"
)

func main() {
    client := aerospace.NewClient("rge_your_api_key")
    
    evidence, err := client.NADCAP.RecordEvidence(&aerospace.NADCAPRequest{
        ProcessType: "HEAT_TREAT",
        PartNumber:  "BA-45678-REV-F",
        LotNumber:   "HT-2024-001",
    })
    
    fmt.Printf("NADCAP evidence: %s\\n", evidence.EvidenceID)
}`,
    },
];
