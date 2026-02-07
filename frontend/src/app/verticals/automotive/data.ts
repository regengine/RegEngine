import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const automotiveIndustryData = {
    industry: 'Automotive',
    description: `The automotive industry is the most compliance-intensive manufacturing sector globally. With 70,000+ certified suppliers under IATF 16949, the standard built on ISO 9001 for automotive quality management, manufacturers face zero-defect expectations from OEMs (GM, Ford, Toyota, Stellantis, VW Group). A single recall can cost $500M-$1B+. Tier 1 suppliers spend $150K-300K annually on certification, surveillance audits (twice yearly), APQP (Advanced Product Quality Planning), PPAP (Production Part Approval Process), and FMEA (Failure Mode Effects Analysis). Manual tracking of control plans, MSA (Measurement System Analysis), and layered process audits is unsustainable at scale.`,

    regulations: [
        {
            name: 'IATF 16949:2016',
            shortName: 'IATF 16949',
            description:
                'Automotive quality management standard combining ISO 9001 with customer-specific requirements from GM, Ford, FCA, VW, and other OEMs. 70,000+ certified suppliers globally. Mandatory for all Tier 1 and many Tier 2 suppliers. Requires APQP, PPAP, control plans, and layered audits.',
            authority: 'International Automotive Task Force (IATF)',
        },
        {
            name: 'ISO 26262:2018',
            shortName: 'ISO 26262',
            description:
                'Functional safety for automotive electrical/electronic systems. Defines Automotive Safety Integrity Levels (ASIL A-D). Required for ADAS, braking systems, steering, powertrain. Misapplication can result in vehicle recalls and criminal liability.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 21434:2021',
            shortName: 'ISO 21434',
            description:
                'Cybersecurity engineering for road vehicles. Addresses lifecycle cybersecurity management, threat analysis, and risk assessment (TARA). Mandatory for connected vehicles and software-defined vehicles in EU (UNECE R155).',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'VDA 6.3',
            shortName: 'VDA 6.3',
            description:
                'German automotive industry process audit standard. Required by VW Group, BMW, Daimler. More rigorous than IATF 16949 for process elements. Requires certified auditors.',
            authority: 'Verband der Automobilindustrie (VDA)',
        },
        {
            name: 'APQP / PPAP',
            shortName: 'APQP/PPAP',
            description:
                'Advanced Product Quality Planning and Production Part Approval Process. Required by all major OEMs. 18 PPAP elements must be submitted before production launch. Failure = launch delays costing $1M+ per day.',
            authority: 'Automotive Industry Action Group (AIAG)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'PPAP Submission Nightmares',
            description:
                '18 PPAP elements (control plans, MSA, process FMEA, dimensional results) tracked across Excel, PDFs, and paper. OEMs reject submissions for missing timestamps or unverifiable measurement data. Re-submissions delay launches.',
            impact: 'high',
        },
        {
            title: 'Layered Process Audit (LPA) Failures',
            description:
                'Daily/weekly shop floor audits required. Paper checklists lose traceability. Cannot prove when audits occurred. IATF auditors issue major non-conformances for missing LPA records.',
            impact: 'high',
        },
        {
            title: 'Multi-OEM Chaos',
            description:
                'GM requires AIAG formats. Ford has unique portals. VW demands VDA 6.3. Toyota has custom PPAP requirements. Suppliers serve 3-5 OEMs with different systems. Zero standardization.',
            impact: 'medium',
        },
        {
            title: 'Expensive Certification Cycles',
            description:
                'IATF 16949 certification: $30K-60K. Two surveillance audits/year at $15K-20K each. Recertification every 3 years. Plus customer-specific audits (GM SQE, Ford Q1). $100K-200K annually.',
            impact: 'high',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'Automotive QMS Software',
            examples: ['Teamcenter Quality', 'SAP QM', 'Omnex QTMS'],
            pros: [
                'APQP workflow automation',
                'PPAP package generation',
                'Control plan management',
                'OEM portal integration (some)',
            ],
            cons: [
                'Extremely expensive ($100K-500K/year)',
                'Long implementation (12-24 months)',
                'No cryptographic verification',
                'Poor multi-OEM support',
            ],
            typicalCost: '$100K-500K/year',
        },
        {
            category: 'Consulting \u0026 Certification Bodies',
            examples: ['VDA QMC', 'IATF Oversight', 'TÜV', 'BSI'],
            pros: [
                'Expert IATF auditors',
                'APQP training',
                'Certification authority',
            ],
            cons: [
                'No technology solution',
                'Manual audit prep (6-8 weeks)',
                'Expensive ($50K-150K per cycle)',
                'Reactive, not preventive',
            ],
            typicalCost: '$150K-250K/year',
        },
        {
            category: 'DIY / Excel-Based',
            examples: ['Excel APQP templates', 'SharePoint', 'Network drives'],
            pros: ['Low initial cost', 'Familiar to teams'],
            cons: [
                'Cannot prove timestamps',
                'OEM submissions rejected',
                'Audit failures',
                'Unmaintainable for multi-site',
            ],
            typicalCost: '$10K-30K/year (labor)',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Cryptographic PPAP packages: Timestamped, immutable 18-element submissions',
            'Unified API for all OEMs: GM, Ford, VW, Toyota formats',
            'Automated LPA tracking: Prove exactly when shop floor audits occurred',
            'Real-time surveillance readiness: 90% faster IATF audit prep',
            'Starting at $6,500/month vs $200K/year for Tier 1 suppliers',
        ],
        tradeoffs: [
            'Requires ERP/MES integration (not standalone QMS)',
            'Best for Tier 1/2 suppliers with API capabilities',
            'Still need certified IATF auditors (we provide evidence, not certification)',
        ],
        notFor: [
            'Tier 3 suppliers without technical resources',
            'Companies requiring full consulting services',
            'Organizations seeking certification body services',
        ],
    } as ApproachComparison,
};

export const automotiveApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/automotive/ppap',
        description: 'Create immutable PPAP (Production Part Approval Process) package with cryptographic verification',
        category: 'PPAP',
        requiresAuth: true,

        requestExample: `curl -X POST https://api.regengine.co/v1/automotive/ppap \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "part_number": "GM-12345-REV-C",
    "supplier_code": "ABC123",
    "oem": "GM",
    "submission_level": 3,
    "elements": {
      "design_records": {...},
      "engineering_change_documents": {...},
      "customer_engineering_approval": {...},
      "design_fmea": {...},
      "process_flow_diagram": {...},
      "process_fmea": {...},
      "control_plan": {...},
      "msa_studies": {...},
      "dimensional_results": {...},
      "material_test_results": {...},
      "initial_process_studies": {...},
      "qualified_lab_documentation": {...},
      "appearance_approval_report": {...},
      "sample_product": {...},
      "master_sample": {...},
      "checking_aids": {...},
      "customer_specific_requirements": {...},
      "pss": {...}
    }
  }'`,
        responseExample: `{
  "ppap_id": "ppap_0193f8a7b2c4d5e6",
  "part_number": "GM-12345-REV-C",
  "contentHash": "sha256:b3f5a8c9d4e1f4a7...",
  "submission_timestamp": "2024-01-26T16:30:00Z",
  "sealed": true,
  "oem_portal_ready": true,
  "elements_complete": 18
}`,
    },
    {
        method: 'POST',
        path: '/v1/automotive/lpa',
        description: 'Record Layered Process Audit (LPA) with cryptographic timestamp and immutability',
        category: 'Audits',
        requiresAuth: true,
        requestExample: `{
  "audit_type": "LPA_LEVEL_1",
  "part_number": "GM-12345-REV-C",
  "production_line": "LINE-03",
  "auditor": "Shift Supervisor - M. Johnson",
  "shift": "DAY_SHIFT",
  "audit_date": "2024-01-26T08:00:00Z",
  "results": [
    {
      "checkpoint": "Torque verification for fastener X",
      "result": "PASS",
      "actual_value": 45.2,
      "spec_range": "40-50 Nm"
    },
    {
      "checkpoint": "Visual inspection for flash",
      "result": "PASS"
    }
  ],
  "overall_score": 100
}`,
        responseExample: `{
  "lpa_id": "lpa_0193f8a7b2c4d5e6",
  "audit_type": "LPA_LEVEL_1",
  "contentHash": "sha256:c9d4e1f4a7b3f5a8...",
  "sealed": true,
  "timestamp_verified": true,
  "overall_score": 100
}`,
    },
    {
        method: 'GET',
        path: '/v1/automotive/iatf-readiness',
        description: 'Real-time IATF 16949 surveillance audit readiness score',
        category: 'Certification',
        requiresAuth: true,
        requestExample: `?facility_id=PLANT-MI-001`,
        responseExample: `{
  "facility_id": "PLANT-MI-001",
  "overall_readiness": 92,
  "standard": "IATF 16949:2016",
  "next_surveillance": "2024-06-15",
  "gaps": [
    {
      "clause": "8.6.1",
      "requirement": "Control plan updates within 30 days of change",
      "status": "MINOR_GAP",
      "recommendation": "Update control plan for ECN-2024-047"
    }
  ],
  "lpa_compliance_30d": 98.5,
  "ppap_submissions_ytd": 12,
  "customer_complaints_ytd": 0
}`,
    },
    {
        method: 'POST',
        path: '/v1/automotive/control-plan',
        description: 'Create or update immutable control plan with revision tracking',
        category: 'Quality Planning',
        requiresAuth: true,
        requestExample: `{
  "part_number": "GM-12345-REV-C",
  "revision": "D",
  "process_steps": [
    {
      "step_number": 10,
      "process_name": "Injection Molding",
      "machine": "ENGEL-250T-01",
      "characteristics": [
        {
          "name": "Wall thickness",
          "spec": "2.5 ± 0.2 mm",
          "control_method": "SPC",
          "sample_size": 5,
          "frequency": "Hourly",
          "reaction_plan": "Adjust process temp"
        }
      ]
    }
  ]
}`,
        responseExample: `{
  "control_plan_id": "cp_0193f8a7b2c4d5e6",
  "part_number": "GM-12345-REV-C",
  "revision": "D",
  "contentHash": "sha256:e1f4a7b3f5a8c9d4...",
  "previous_revision_hash": "sha256:f4a7b3f5a8c9d4e1...",
  "sealed": true
}`,
    },
    {
        method: 'POST',
        path: '/v1/automotive/8d-report',
        description: 'Create immutable 8D problem-solving report (customer complaint response)',
        category: 'Corrective Action',
        requiresAuth: true,
        requestExample: `{
  "complaint_id": "GM-COMP-2024-001",
  "part_number": "GM-12345-REV-C",
  "customer": "GM",
  "d1_team": ["Quality Engineer", "Process Engineer", "Production Supervisor"],
  "d2_problem_description": "Dimensional variance on Feature X",
  "d3_interim_containment": "100% inspection at receiving",
  "d4_root_cause": "Tooling wear beyond tolerance",
  "d5_permanent_corrective_actions": ["Replace tooling", "Reduce PM interval"],
  "d6_implementation_date": "2024-01-27",
  "d7_prevent_recurrence": ["Update FMEA", "Add to control plan"],
  "d8_team_recognition": "Team recognized for 24hr response"
}`,
        responseExample: `{
  "report_id": "8d_0193f8a7b2c4d5e6",
  "complaint_id": "GM-COMP-2024-001",
  "contentHash": "sha256:a7b3f5a8c9d4e1f4...",
  "sealed": true,
  "submitted_to_customer": false
}`,
    },
];

export const automotiveSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/automotive-sdk',
        description: 'Type-safe SDK for PPAP and IATF compliance',
        quickstartCode: `import { AutomotiveCompliance } from '@regengine/automotive-sdk';

const auto = new AutomotiveCompliance('rge_your_api_key');

// Create immutable PPAP package
const ppap = await auto.ppap.create({
  part_number: 'GM-12345-REV-C',
  supplier_code: 'ABC123',
  oem: 'GM',
  submission_level: 3,
  elements: {
    control_plan: { /* ... */ },
    dimensional_results: { /* ... */ },
    // ... all 18 elements
  }
});

console.log('✅ PPAP sealed:', ppap.ppap_id);
console.log('🔒 Hash:', ppap.contentHash);
console.log('📋 OEM ready:', ppap.oem_portal_ready);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-automotive',
        description: 'Python SDK for MES/ERP integration',
        quickstartCode: `from regengine.automotive import AutomotiveCompliance

auto = AutomotiveCompliance(api_key='rge_your_api_key')

# Record Layered Process Audit
lpa = auto.lpa.create(
    audit_type='LPA_LEVEL_1',
    part_number='GM-12345-REV-C',
    production_line='LINE-03',
    auditor='Shift Supervisor - M. Johnson',
    results=[
        {'checkpoint': 'Torque verification', 'result': 'PASS'}
    ],
    overall_score=100
)

print(f'LPA sealed: {lpa.lpa_id}')
print(f'Timestamp verified: {lpa.timestamp_verified}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/automotive-sdk-go',
        description: 'Go SDK for high-throughput quality data',
        quickstartCode: `package main

import (
    "github.com/regengine/automotive-sdk-go"
)

func main() {
    client := automotive.NewClient("rge_your_api_key")
    
    report, err := client.EightD.Create(&automotive.EightDRequest{
        ComplaintID: "GM-COMP-2024-001",
        PartNumber:  "GM-12345-REV-C",
        D4RootCause: "Tooling wear beyond tolerance",
    })
    
    fmt.Printf("8D Report: %s\\n", report.ReportID)
}`,
    },
];
