import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const healthcareIndustryData = {
    industry: 'Healthcare',
    description: `Healthcare data breaches cost $10.93M on average—the highest of any industry (IBM Security, 2023). HIPAA's Security Rule requires "reasonable and appropriate" safeguards for ePHI, but enforcement is reactive. 83% of breaches are discovered months after occurrence, making forensic investigation nearly impossible. With OCR fines reaching $16M+ per settlement, behavioral surveillance and immutable audit logs are no longer optional—they're existential.`,

    regulations: [
        {
            name: 'HIPAA Security Rule',
            shortName: 'HIPAA',
            description:
                'Requires technical, administrative, and physical safeguards for electronic Protected Health Information (ePHI). Mandates access controls, audit controls, and integrity controls.',
            authority: 'U.S. Department of Health and Human Services (HHS)',
        },
        {
            name: 'HITECH Act',
            shortName: 'HITECH',
            description:
                'Strengthens HIPAA enforcement with mandatory breach notification (≥500 individuals requires public disclosure). Increases penalties to $50K per violation, $1.5M annual maximum.',
            authority: 'U.S. Department of Health and Human Services (HHS)',
        },
        {
            name: 'State Privacy Laws (CCPA/CMIA)',
            shortName: 'CCPA',
            description:
                'California Consumer Privacy Act and Confidentiality of Medical Information Act. Grants patients rights to access, delete, and opt-out of data sales.',
            authority: 'California Attorney General',
        },
        {
            name: 'OCR Audit Protocol',
            shortName: 'OCR',
            description:
                'Office for Civil Rights conducts HIPAA compliance audits requiring 6+ years of access logs, risk assessments, and evidence of security controls.',
            authority: 'Office for Civil Rights (OCR)',
        },
        {
            name: 'ISO 13485:2016',
            shortName: 'ISO 13485',
            description:
                'Medical Devices - Quality Management Systems. Often mandatory to market medical devices in major jurisdictions. Aligns with FDA QSR and EU MDR requirements. Addresses product safety and efficacy through design controls, risk management, and post-market surveillance. ~30,000 certifications worldwide.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 9001:2015',
            shortName: 'ISO 9001',
            description:
                'Quality Management Systems - Requirements. Hospitals implementing ISO 9001 have documented reductions in clinical errors. One hospital saw patient satisfaction rise 20% within a year due to more consistent care and fewer mistakes. Provides foundation for clinical quality improvement.',
            authority: 'International Organization for Standardization (ISO)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'Behavioral Anomaly Detection',
            description:
                'Traditional audit logs capture "who accessed what," but not "why." Cannot detect VIP snooping, excessive access, or role misuse in real-time. Most breaches are insider threats.',
            impact: 'high',
        },
        {
            title: 'Mutable Audit Logs',
            description:
                'EHR access logs can be deleted or altered by administrators. OCR audits require proof that logs are tamper-evident. Spreadsheets and database logs are inadmissible evidence.',
            impact: 'high',
        },
        {
            title: '6-Year Audit Readiness',
            description:
                'OCR requires evidence going back 6+ years. Logs are often deleted after 90 days. Manual compilation takes weeks. No centralized system of record for compliance.',
            impact: 'medium',
        },
        {
            title: 'Cross-System Correlation',
            description:
                'Patients interact with EHR, billing, lab systems, pharmacy, and more. Cannot correlate access patterns across systems. Siloed logs prevent holistic risk analysis.',
            impact: 'medium',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'SIEM Tools',
            examples: ['Splunk', 'LogRhythm', 'IBM QRadar'],
            pros: ['Real-time monitoring', 'Advanced analytics', 'Cross-system correlation'],
            cons: [
                'Extremely expensive ($100K-500K/year)',
                'Requires security expertise',
                'Logs still mutable',
                'Not healthcare-specific',
            ],
            typicalCost: '$100K-500K/year',
        },
        {
            category: 'Access Governance Platforms',
            examples: ['SailPoint', 'Saviynt', 'Okta'],
            pros: ['Identity-focused', 'Role-based access control', 'Certification workflows'],
            cons: [
                'Not behavioral (only role-based)',
                'No real-time anomaly detection',
                'Expensive implementations',
                'Limited audit trail',
            ],
            typicalCost: '$50K-200K/year',
        },
        {
            category: 'EHR Native Logging',
            examples: ['Epic, Cerner, Meditech'],
            pros: ['Built-in', 'No additional cost', 'Native integration'],
            cons: [
                'Logs are mutable',
                'Limited retention (30-90 days)',
                'No behavioral heuristics',
                'Admin can delete logs',
            ],
            typicalCost: '$0 (included)',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'Real-time behavioral heuristics: Detect VIP snooping, excessive access instantly',
            'Immutable audit logs: Database-enforced, cannot be deleted or altered',
            'Clinical Risk Monitor dashboard: Live departmental risk heatmaps',
            'API-driven integration: Works with any EHR (Epic, Cerner, etc.)',
            'Cost-effective: $3K-10K/month vs $100K+ SIEM tools',
        ],
        tradeoffs: [
            'Requires EHR API integration (HL7 FHIR, proprietary APIs)',
            'Heuristics are statistical (not ML-based, to avoid false positives)',
            'Self-service setup (less hand-holding than consultants)',
        ],
        notFor: [
            'Practices without API access to EHR data',
            'Organizations requiring on-premise air-gapped solutions',
            'Teams without technical implementation resources',
        ],
    } as ApproachComparison,
};

export const healthcareApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/healthcare/access-log',
        description: 'Log an ePHI access event with immutable timestamping',
        category: 'Access Logging',
        requiresAuth: true,
        requestExample: `{
  "userId": "dr_house_1234",
  "userRole": "MD",
  "action": "VIEW",
  "patientId": "P-VIP-001",
  "recordType": "MEDICAL_RECORD",
  "timestamp": "2024-01-26T10:00:00Z",
  "facilityId": "ER-DEPT-01"
}`,
        responseExample: `{
  "logId": "log_0193f8a7b2c4d5e6",
  "riskScore": 85,
  "flagged": true,
  "reason": "VIP_SNOOPING_DETECTED",
  "sealed": true,
  "contentHash": "sha256:a3f5b8c9..."
}`,
    },
    {
        method: 'GET',
        path: '/v1/healthcare/risk-heatmap',
        description: 'Get real-time departmental risk heatmap for Clinical Risk Monitor',
        category: 'Risk Monitoring',
        requiresAuth: true,
        responseExample: `{
  "departments": [
    {
      "name": "ER (Emergency)",
      "riskScore": 85,
      "status": "CRITICAL",
      "anomalies": ["VIP_SNOOPING", "EXCESSIVE_ACCESS"]
    }
  ],
  "generatedAt": "2024-01-26T10:05:00Z"
}`,
    },
    {
        method: 'GET',
        path: '/v1/healthcare/access-stream',
        description: 'Get live access stream for real-time monitoring',
        category: 'Access Logging',
        requiresAuth: true,
        responseExample: `{
  "events": [
    {
      "user": "Dr. House",
      "action": "VIEW",
      "patient": "VIP_001",
      "status": "FLAGGED",
      "timestamp": "2024-01-26T10:42:01Z"
    }
  ]
}`,
    },
    {
        method: 'POST',
        path: '/v1/healthcare/audit-export',
        description: 'Export OCR-compliant audit report for compliance audits',
        category: 'Compliance Export',
        requiresAuth: true,
        requestExample: `{
  "startDate": "2018-01-01",
  "endDate": "2024-01-26",
  "includeAllDepartments": true,
  "format": "PDF"
}`,
        responseExample: `{
  "exportId": "exp_0193f8a7b2c4d5e9",
  "downloadUrl": "https://api.regengine.co/downloads/exp_...",
  "recordCount": 12847,
  "expiresAt": "2024-01-27T10:15:00Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/healthcare/iso-13485-device-tracking',
        description: 'Track medical device quality events for ISO 13485 compliance',
        category: 'ISO Compliance',
        requiresAuth: true,
        requestExample: `{
        "device_id": "DEV-PUMP-001",
        "device_name": "Infusion Pump Model X",
        "event_type": "DESIGN_CHANGE",
        "change_description": "Updated flow rate algorithm",
        "risk_analysis_id": "FMEA-2024-001",
        "regulatory_notification_required": true,
        "fda_510k_impact": true
    }`,
        responseExample: `{
        "tracking_id": "iso13485_0193f8a7b2c4d5e6",
        "device_id": "DEV-PUMP-001",
        "dhf_updated": true,
        "dhr_referenced": true,
        "post_market_surveillance_triggered": true,
        "compliance_status": "COMPLIANT"
    }`,
    },
    {
        method: 'GET',
        path: '/v1/healthcare/iso-9001-quality-metrics',
        description: 'Get ISO 9001 quality management metrics for clinical operations',
        category: 'ISO Compliance',
        requiresAuth: true,
        responseExample: `{
        "standard": "ISO 9001:2015",
        "overall_quality_score": 87,
        "patient_satisfaction": {
            "current": 4.6,
            "baseline": 3.8,
            "improvement_percentage": 21
        },
        "clinical_errors": {
            "current_rate": 2.1,
            "baseline_rate": 5.3,
            "reduction_percentage": 60
        },
        "process_improvements": 42,
        "corrective_actions_closed": 38,
        "audit_findings": 3
    }`,
    },
];

export const healthcareSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/healthcare-sdk',
        description: 'Type-safe SDK for EHR integrations',
        quickstartCode: `import { HealthcareCompliance } from '@regengine/healthcare-sdk';

const healthcare = new HealthcareCompliance('rge_your_api_key');

// Log access event
const log = await healthcare.accessLog.create({
    userId: 'dr_house_1234',
    userRole: 'MD',
    action: 'VIEW',
    patientId: 'P-VIP-001'
});

console.log('Risk score:', log.riskScore);
console.log('Flagged:', log.flagged); `,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-healthcare',
        description: 'Python SDK for automation and integration',
        quickstartCode: `from regengine.healthcare import HealthcareCompliance

hc = HealthcareCompliance(api_key = 'rge_your_api_key')

# Log access event
log = hc.access_log.create(
    user_id = 'dr_house_1234',
    user_role = 'MD',
    action = 'VIEW',
    patient_id = 'P-VIP-001'
)

print(f'Risk score: {log.risk_score}')
print(f'Flagged: {log.flagged}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/healthcare-sdk-go',
        description: 'Go SDK for high-performance applications',
        quickstartCode: `package main

import(
    "github.com/regengine/healthcare-sdk-go"
)

func main() {
    client:= healthcare.NewClient("rge_your_api_key")

    log, _ := client.AccessLog.Create(& healthcare.AccessLogRequest{
        UserID: "dr_house_1234",
        UserRole: "MD",
        Action: "VIEW",
        PatientID: "P-VIP-001",
    })

    fmt.Printf("Risk: %d\\n", log.RiskScore)
} `,
    },
];
