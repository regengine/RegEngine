import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const constructionIndustryData = {
    industry: 'Construction',
    description: `The global construction industry generates $10+ trillion annually while managing complex regulatory compliance across quality (ISO 9001), environmental (ISO 14001), and safety (ISO 45001) standards. With Building Information Modeling (BIM) becoming mandatory via ISO 19650 in the EU and UK, contractors must maintain digital twin models with cryptographic change tracking. Construction sites face 20-30% higher injury rates than other industries, making ISO 45001 critical for insurance and liability protection. Large projects (infrastructure, commercial high-rises) require simultaneous compliance with 10+ standards across quality, safety, environmental, and information management. Manual documentation consumes 15-20% of project budgets and is a leading cause of disputes, delays, and cost overruns.`,

    regulations: [
        {
            name: 'ISO 19650:2018',
            shortName: 'ISO 19650',
            description:
                'Organization and digitization of information about buildings and civil engineering works, including BIM. Mandates collaborative workflows, Common Data Environment (CDE), and information management protocols. Required for UK public projects. Growing adoption in EU, Australia, Singapore.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 9001:2015',
            shortName: 'ISO 9001',
            description:
                'Quality management system for construction contractors and subcontractors. Ensures process control, defect prevention, and client satisfaction. Required by most commercial and infrastructure clients. 1+ million certifications globally.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 14001:2015',
            shortName: 'ISO 14001',
            description:
                'Environmental management for construction operations. Controls dust, noise, waste, and emissions. Required for LEED certification and government contracts. Reduces environmental fines by 40-60%.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 45001:2018',
            shortName: 'ISO 45001',
            description:
                'Occupational health and safety management. Replaces OHSAS 18001. Construction has 2-3x injury rates vs other industries. ISO 45001 reduces incidents 30-50%, lowers insurance premiums 15-25%, and protects against liability.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'OSHA 1926',
            shortName: 'OSHA 1926',
            description:
                'U.S. occupational safety regulations for construction. Covers scaffolding, fall protection, electrical safety, excavation. Violations result in $15K-$140K fines per incident. Willful violations can trigger criminal prosecution.',
            authority: 'Occupational Safety and Health Administration (OSHA)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'BIM Data Integrity \u0026 Change Control',
            description:
                'ISO 19650 requires Common Data Environment (CDE) with version control. Contractors track 1000+ design changes per project. Excel-based RFI logs cannot prove when changes occurred. Client disputes over scope creep.',
            impact: 'high',
        },
        {
            title: 'Multi-Standard Certification Chaos',
            description:
                'Large contractors need ISO 9001 + 14001 + 45001 + 19650 simultaneously. Four separate audit cycles. Overlapping requirements. No unified evidence repository. $150K-300K annual certification costs.',
            impact: 'high',
        },
        {
            title: 'Site Safety Documentation Failures',
            description:
                'Daily toolbox talks, safety inspections, and incident reports on paper. Cannot prove completion to OSHA auditors. Missing records = automatic violations and fines. Insurance claims denied for lack of documentation.',
            impact: 'high',
        },
        {
            title: 'Subcontractor Compliance Gaps',
            description:
                '20-50 subcontractors per project with varying safety standards. General contractors liable for sub violations. Manual tracking of sub certifications, safety training, and insurance is error-prone.',
            impact: 'medium',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'BIM \u0026 CDE Platforms',
            examples: ['Autodesk BIM 360', 'Procore', 'Trimble Connect'],
            pros: [
                'BIM collaboration',
                'Document management',
                'RFI \u0026 submittals',
                'Mobile access',
            ],
            cons: [
                'No ISO certification focus',
                'Poor audit trail integrity',
                'Expensive ($50K-200K/year)',
                'No cryptographic verification',
            ],
            typicalCost: '$50K-200K/year',
        },
        {
            category: 'Safety Management Software',
            examples: ['SafetyCulture (iAuditor)', 'Procore Safety', 'Safety Reports'],
            pros: [
                'Digital inspections',
                'Incident reporting',
                'Mobile forms',
            ],
            cons: [
                'Not ISO 45001-specific',
                'Cannot prove tamper-proof records',
                'Poor multi-standard integration',
            ],
            typicalCost: '$10K-40K/year',
        },
        {
            category: 'Certification Consultancies',
            examples: ['BSI', 'TÜV', 'SGS', 'Bureau Veritas'],
            pros: [
                'ISO certification expertise',
                'Audit services',
                'Gap analysis',
            ],
            cons: [
                'No technology platform',
                'Manual evidence collection',
                'Expensive ($40K-80K per standard)',
                '6-12 month certification timeline',
            ],
            typicalCost: '$150K-300K/year (all standards)',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Unified API for ISO 9001 + 14001 + 45001 + 19650',
            'Cryptographic BIM change logs: Prove when RFIs and design changes occurred',
            'Immutable safety records: Toolbox talks, inspections, incident reports',
            'Automated multi-standard audit readiness: 85% faster prep',
            'Starting at $5,500/month vs $300K/year for large contractors',
        ],
        tradeoffs: [
            'Requires integration with BIM platforms or project management systems',
            'Best for contractors with API/IT capabilities',
            'Certification bodies still required (we provide evidence, not certification)',
        ],
        notFor: [
            'Small contractors without technical resources',
            'Organizations requiring full consulting services',
            'Companies seeking certification body services',
        ],
    } as ApproachComparison,
};

export const constructionApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/construction/bim-change',
        description: 'Record BIM design change with cryptographic timestamp per ISO 19650 requirements',
        category: 'BIM',
        requiresAuth: true,

        requestExample: `curl -X POST https://api.regengine.co/v1/construction/bim-change \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "project_id": "PROJ-2024-001",
    "rfi_number": "RFI-456",
    "change_description": "Structural steel beam revised from W12x40 to W12x45",
    "affected_models": ["STRUCT-L3-REV-D", "ARCH-L3-REV-C"],
    "requested_by": "Structural Engineer - A. Chen",
    "approved_by": "Project Manager - K. Davis",
    "approval_date": "2024-01-26",
    "iso19650_workflow_stage": "COORDINATION",
    "cde_container": "WIP"
  }'`,
        responseExample: `{
  "change_id": "bim_0193f8a7b2c4d5e6",
  "project_id": "PROJ-2024-001",
  "rfi_number": "RFI-456",
  "contentHash": "sha256:c9d4e1f4a7b3f5a8...",
  "timestamp": "2024-01-26T14:30:00Z",
  "sealed": true,
  "iso19650_compliant": true
}`,
    },
    {
        method: 'POST',
        path: '/v1/construction/safety-inspection',
        description: 'Create immutable safety inspection record with OSHA 1926 compliance tracking',
        category: 'Safety',
        requiresAuth: true,
        requestExample: `{
  "project_id": "PROJ-2024-001",
  "inspection_type": "SCAFFOLD_INSPECTION",
  "site_location": "Building A - Level 5",
  "inspector": "Safety Officer - M. Rodriguez",
  "inspection_date": "2024-01-26T08:00:00Z",
  "checklist_items": [
    {
      "item": "Scaffold tags in place and current",
      "osha_ref": "1926.451(f)(3)",
      "status": "PASS"
    },
    {
      "item": "Fall protection at 6ft+ heights",
      "osha_ref": "1926.501(b)(1)",
      "status": "PASS"
    },
    {
      "item": "Guardrails properly installed",
      "osha_ref": "1926.451(g)(4)",
      "status": "FAIL",
      "corrective_action": "Install missing midrail on north side"
    }
  ],
  "overall_status": "CONDITIONAL_APPROVAL"
}`,
        responseExample: `{
  "inspection_id": "saf_0193f8a7b2c4d5e6",
  "project_id": "PROJ-2024-001",
  "contentHash": "sha256:e1f4a7b3f5a8c9d4...",
  "sealed": true,
  "timestamp_verified": true,
  "osha_compliant": false,
  "corrective_actions_required": 1
}`,
    },
    {
        method: 'POST',
        path: '/v1/construction/quad-cert-snapshot',
        description: 'Create unified snapshot for ISO 9001 + 14001 + 45001 + 19650 compliance',
        category: 'Certification',
        requiresAuth: true,
        requestExample: `{
  "project_id": "PROJ-2024-001",
  "contractor_id": "CONT-001",
  "snapshot_type": "QUARTERLY_SURVEILLANCE",
  "standards": ["ISO 9001:2015", "ISO 14001:2015", "ISO 45001:2018", "ISO 19650:2018"],
  "quality_metrics": {
    "ncr_count_30d": 2,
    "client_satisfaction_score": 4.7,
    "defect_rate_pct": 0.8
  },
  "environmental_metrics": {
    "waste_diverted_from_landfill_pct": 82,
    "dust_complaints": 0,
    "noise_violations": 0
  },
  "safety_metrics": {
    "lost_time_incidents": 0,
    "near_miss_reports": 12,
    "safety_training_compliance_pct": 97.5
  },
  "bim_metrics": {
    "model_coordination_clash_count": 3,
    "rfi_response_time_avg_days": 2.4,
    "design_changes_tracked": 47
  }
}`,
        responseExample: `{
  "snapshot_id": "snap_0193f8a7b2c4d5e6",
  "project_id": "PROJ-2024-001",
  "standards_covered": 4,
  "contentHash": "sha256:a7b3f5a8c9d4e1f4...",
  "audit_ready": true,
  "certification_bodies": ["BSI", "TUV", "DNV"],
  "next_surveillance": "2024-04-26"
}`,
    },
    {
        method: 'POST',
        path: '/v1/construction/toolbox-talk',
        description: 'Record daily toolbox talk with attendee verification and ISO 45001 compliance',
        category: 'Safety',
        requiresAuth: true,
        requestExample: `{
  "project_id": "PROJ-2024-001",
  "date": "2024-01-26",
  "topic": "Fall Protection Requirements for Elevated Work",
  "presenter": "Foreman - J. Williams",
  "attendees": [
    {"name": "Worker A", "badge": "12345"},
    {"name": "Worker B", "badge": "12346"}
  ],
  "duration_minutes": 15,
  "hazards_discussed": ["Falls from height", "Scaffold use", "Harness inspection"],
  "questions_raised": 2
}`,
        responseExample: `{
  "toolbox_id": "tbx_0193f8a7b2c4d5e6",
  "project_id": "PROJ-2024-001",
  "contentHash": "sha256:f4a7b3f5a8c9d4e1...",
  "sealed": true,
  "attendee_count": 2,
  "iso45001_compliant": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/construction/subcontractor-compliance',
        description: 'Track subcontractor ISO certifications, insurance, and safety performance',
        category: 'Subcontractor Management',
        requiresAuth: true,
        requestExample: `?project_id=PROJ-2024-001`,
        responseExample: `{
  "project_id": "PROJ-2024-001",
  "subcontractors": [
    {
      "name": "ABC Steel Erectors",
      "iso9001_status": "CURRENT",
      "iso45001_status": "CURRENT",
      "insurance_expiry": "2024-12-31",
      "safety_incidents_ytd": 0,
      "compliance_score": 98
    },
    {
      "name": "XYZ Concrete",
      "iso9001_status": "EXPIRED",
      "iso45001_status": "NOT_CERTIFIED",
      "insurance_expiry": "2024-06-30",
      "safety_incidents_ytd": 1,
      "compliance_score": 62
    }
  ],
  "overall_compliance": 80,
  "high_risk_subs": 1
}`,
    },
];

export const constructionSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/construction-sdk',
        description: 'Type-safe SDK for construction compliance',
        quickstartCode: `import { ConstructionCompliance } from '@regengine/construction-sdk';

const construction = new ConstructionCompliance('rge_your_api_key');

// Record BIM design change
const change = await construction.bim.recordChange({
  project_id: 'PROJ-2024-001',
  rfi_number: 'RFI-456',
  change_description: 'Structural steel beam revised',
  affected_models: ['STRUCT-L3-REV-D'],
  approved_by: 'Project Manager - K. Davis',
  approval_date: new Date().toISOString()
});

console.log('✅ BIM change sealed:', change.change_id);
console.log('🔒 Hash:', change.contentHash);
console.log('📋 ISO 19650 compliant:', change.iso19650_compliant);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-construction',
        description: 'Python SDK for project management integration',
        quickstartCode: `from regengine.construction import ConstructionCompliance

construction = ConstructionCompliance(api_key='rge_your_api_key')

# Record safety inspection
inspection = construction.safety.create_inspection(
    project_id='PROJ-2024-001',
    inspection_type='SCAFFOLD_INSPECTION',
    inspector='Safety Officer - M. Rodriguez',
    checklist_items=[
        {'item': 'Scaffold tags current', 'status': 'PASS'},
        {'item': 'Fall protection present', 'status': 'PASS'}
    ]
)

print(f'Inspection sealed: {inspection.inspection_id}')
print(f'OSHA compliant: {inspection.osha_compliant}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/construction-sdk-go',
        description: 'Go SDK for field data collection',
        quickstartCode: `package main

import (
    "github.com/regengine/construction-sdk-go"
)

func main() {
    client := construction.NewClient("rge_your_api_key")
    
    toolbox, err := client.Safety.RecordToolboxTalk(&construction.ToolboxRequest{
        ProjectID: "PROJ-2024-001",
        Topic:     "Fall Protection Requirements",
        Presenter: "Foreman - J. Williams",
    })
    
    fmt.Printf("Toolbox talk: %s\\n", toolbox.ToolboxID)
}`,
    },
];
