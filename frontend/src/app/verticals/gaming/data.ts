import {
    RegulationInfo,
    Challenge,
    MarketplaceSolution,
    ApproachComparison,
} from '@/components/verticals/IndustryOverviewSection';
import { ApiEndpoint, SdkExample } from '@/components/verticals/ApiReferenceSection';

export const gamingIndustryData = {
    industry: 'Gaming & Hospitality',
    description: `Gaming and hospitality companies operate under strict gaming commission oversight. Nevada, New Jersey, and tribal gaming authorities require meticulous record-keeping of transactions, player activity, and responsible gaming interventions. A single compliance failure—such as failing to honor a self-exclusion—can result in license suspension, $100K+ fines, or revocation affecting a $500M+ annual revenue property. With 28 states now offering legal gaming, compliance complexity is multiplying.`,

    regulations: [
        {
            name: 'Nevada Gaming Control Board Reg 5 & 6',
            shortName: 'NGCB Reg 5/6',
            description: 'Minimum Internal Control Standards. Requires comprehensive accounting records, surveillance integration, and responsible gaming compliance.',
            authority: 'Nevada Gaming Control Board',
        },
        {
            name: 'New Jersey Technical Standards',
            shortName: 'NJ Tech Standards',
            description: 'DGE Technical Standards for casino gaming systems. Mandates secure transaction logs, player protection, and audit trail preservation.',
            authority: 'New Jersey Division of Gaming Enforcement (DGE)',
        },
        {
            name: 'Indian Gaming Regulatory Act (IGRA)',
            shortName: 'IGRA',
            description: 'Federal framework for tribal gaming. Class II and III gaming require NIGC approval and comprehensive compliance programs.',
            authority: 'National Indian Gaming Commission (NIGC)',
        },
        {
            name: 'FinCEN (Anti-Money Laundering)',
            shortName: 'AML/BSA',
            description: 'Bank Secrecy Act compliance. Casinos must report transactions >$10K (CTR) and suspicious activity (SAR). Violations result in federal prosecution.',
            authority: 'Financial Crimes Enforcement Network (FinCEN)',
        },
        {
            name: 'ISO 31000:2018',
            shortName: 'ISO 31000',
            description:
                'Risk Management - Guidelines. Provides framework for identifying, assessing, and mitigating operational risks in gaming operations. Helps casinos systematically address risks from problem gambling, AML, regulatory compliance, and operational integrity. ~10,000 organizations worldwide use ISO 31000 principles.',
            authority: 'International Organization for Standardization (ISO)',
        },
        {
            name: 'ISO 9001:2015',
            shortName: 'ISO 9001',
            description:
                'Quality Management Systems - Requirements. Provides framework for consistent service delivery, customer satisfaction, and operational excellence in hospitality operations. Casinos implementing ISO 9001 report improved guest satisfaction and operational efficiency.',
            authority: 'International Organization for Standardization (ISO)',
        },
    ] as RegulationInfo[],

    challenges: [
        {
            title: 'Transaction Log Retention (5+ Years)',
            description: 'Must preserve every bet, win, loss for 5+ years. Casino Management Systems generate millions of transactions daily. Storage and retrieval are expensive.',
            impact: 'high',
        },
        {
            title: 'Responsible Gaming Compliance',
            description: 'Track self-exclusions, interventions, escalations. If a self-excluded player gambles, the casino is liable. No centralized cross-property tracking.',
            impact: 'high',
        },
        {
            title: 'Surveillance Integration',
            description: 'Gaming commissions require correlating video surveillance with transaction data. Manual correlation for investigations takes days. No automated timeline.',
            impact: 'medium',
        },
        {
            title: 'Multi-Jurisdiction Complexity',
            description: 'Different rules for Nevada, NJ, tribal lands, and 25+ other states. No standard compliance framework. Must manage jurisdiction-specific requirements.',
            impact: 'medium',
        },
    ] as Challenge[],

    marketplaceSolutions: [
        {
            category: 'Casino Management Systems (CMS)',
            examples: ['IGT Advantage', 'Konami Synkros', 'Aristocrat Oasis'],
            pros: ['Integrated', 'Gaming commission certified', 'Real-time player tracking'],
            cons: ['Monolithic', 'Limited APIs', 'Vendor lock-in', 'Expensive ($500K-2M implementations)'],
            typicalCost: '$500K-2M (implementation)',
        },
        {
            category: 'Compliance Software',
            examples: ['Proprietary gaming compliance tools'],
            pros: ['Jurisdiction-specific', 'Audit-ready reports', 'Surveillance integration'],
            cons: ['Expensive', 'Not API-driven', 'Limited extensibility', 'Vendor lock-in'],
            typicalCost: '$100K-300K/year',
        },
        {
            category: 'Manual Log Books',
            examples: ['Paper-based tracking', 'Excel spreadsheets'],
            pros: ['Low cost', 'Commission-accepted (legacy)', 'Simple'],
            cons: ['Error-prone', 'Not searchable', 'Cannot correlate data', 'Labor-intensive'],
            typicalCost: '$10K-50K/year (labor)',
        },
    ] as MarketplaceSolution[],

    ourApproach: {
        better: [
            'API-first integration with existing CMS platforms',
            'Immutable transaction logs with cryptographic integrity',
            'Cross-property self-exclusion tracking',
            'Automated surveillance timeline correlation',
            'Cost-effective: $5K-15K/month vs $500K+ CMS replacements',
        ],
        tradeoffs: [
            'Requires integration work (not a replacement CMS)',
            'Works best with modern CMS platforms offering APIs',
            'Self-service model (less hand-holding than full implementations)',
        ],
        notFor: [
            'Casinos without API access to transaction systems',
            'Properties requiring monolithic CMS replacement',
            'Organizations without technical integration resources',
        ],
    } as ApproachComparison,
};


export const gamingApiEndpoints: ApiEndpoint[] = [
    {
        method: 'POST',
        path: '/v1/gaming/transaction-log',
        description: 'Create immutable record of casino transaction with cryptographic verification',
        category: 'Transaction Management',
        requiresAuth: true,
        requestExample: `curl -X POST https://api.regengine.co/v1/gaming/transaction-log \\
  -H "X-RegEngine-API-Key: rge_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "transaction_id": "TXN-20240126-001234",
    "transaction_type": "SLOT_MACHINE_PAYOUT",
    "player_id": "P-VIP-12345",
    "machine_id": "SLOT-A-042",
    "amount_cents": 250000,
    "timestamp": "2024-01-26T10:00:00Z",
    "casino_location": "Vegas Main Floor",
    "jurisdiction": "Nevada"
  }'`,
        responseExample: `{
  "log_id": "log_0193f8a7b2c4d5e6",
  "transaction_id": "TXN-20240126-001234",
  "content_hash": "sha256:a3f5b8c9d2e1f4a7...",
  "sealed": true,
  "created_at": "2024-01-26T10:00:01Z",
  "retention_until": "2029-01-26",
  "jurisdiction_compliant": true
}`,
    },
    {
        method: 'GET',
        path: '/v1/gaming/transaction-log/:id',
        description: 'Retrieve a specific transaction log by ID',
        category: 'Transaction Management',
        requiresAuth: true,
        responseExample: `{
  "log_id": "log_0193f8a7b2c4d5e6",
  "transaction_id": "TXN-20240126-001234",
  "transaction_type": "SLOT_MACHINE_PAYOUT",
  "player_id": "P-VIP-12345",
  "amount_cents": 250000,
  "content_hash": "sha256:a3f5b8c9d2e1f4a7...",
  "sealed": true,
  "created_at": "2024-01-26T10:00:01Z",
  "jurisdiction_compliant": true
}`,
    },
    {
        method: 'POST',
        path: '/v1/gaming/self-exclusion',
        description: 'Log responsible gaming self-exclusion event',
        category: 'Responsible Gaming',
        requiresAuth: true,
        requestExample: `{
  "player_id": "P-123456",
  "exclusion_type": "PERMANENT",
  "reason": "PLAYER_REQUEST",
  "effective_date": "2024-01-26",
  "casino_locations": ["Vegas Main Floor", "Reno Property"],
  "jurisdiction": "Nevada"
}`,
        responseExample: `{
  "exclusion_id": "excl_0193f8a7b2c4d5e6",
  "player_id": "P-123456",
  "status": "ACTIVE",
  "effective_date": "2024-01-26",
  "permanent": true,
  "created_at": "2024-01-26T10:00:01Z"
}`,
    },
    {
        method: 'GET',
        path: '/v1/gaming/surveillance-timeline',
        description: 'Correlate transactions with surveillance footage timestamps',
        category: 'Surveillance Integration',
        requiresAuth: true,
        requestExample: `?player_id=P-VIP-12345&start_time=2024-01-26T09:00:00Z&end_time=2024-01-26T11:00:00Z`,
        responseExample: `{
  "player_id": "P-VIP-12345",
  "timeline": [
    {
      "timestamp": "2024-01-26T10:00:00Z",
      "event_type": "TRANSACTION",
      "transaction_id": "TXN-20240126-001234",
      "machine_id": "SLOT-A-042",
      "camera_ids": ["CAM-FL1-042", "CAM-FL1-OVERHEAD"]
    },
    {
      "timestamp": "2024-01-26T10:15:00Z",
      "event_type": "CAGE_TRANSACTION",
      "amount_cents": 250000,
      "camera_ids": ["CAM-CAGE-01"]
    }
  ],
  "total_events": 2
}`,
    },
    {
        method: 'POST',
        path: '/v1/gaming/compliance-export',
        description: 'Export gaming commission compliance report',
        category: 'Audit & Reporting',
        requiresAuth: true,
        requestExample: `{
  "jurisdiction": "Nevada",
  "report_type": "QUARTERLY",
  "period_start": "2024-01-01",
  "period_end": "2024-03-31",
  "include_surveillance": true,
  "format": "PDF"
}`,
        responseExample: `{
  "export_id": "exp_0193f8a7b2c4d5e6",
  "status": "GENERATING",
  "transaction_count": 1247589,
  "player_count": 42891,
  "download_url": null,
  "estimated_completion": "2024-01-26T10:30:00Z"
}`,
    },
    {
        method: 'POST',
        path: '/v1/gaming/iso-31000-risk-assessment',
        description: 'Log ISO 31000 risk assessment for gaming operations',
        category: 'ISO Compliance',
        requiresAuth: true,
        requestExample: `{
  "casino_location": "Vegas Main Floor",
  "risk_type": "PROBLEM_GAMBLING",
  "risk_level": "MEDIUM",
  "player_id": "P-RISK-789",
  "indicators": ["EXCESSIVE_PLAY_TIME", "INCREASING_WAGERS"],
  "intervention_required": true,
  "responsible_gaming_alert": true
}`,
        responseExample: `{
  "risk_id": "iso31000_0193f8a7b2c4d5e6",
  "casino_location": "Vegas Main Floor",
  "risk_score": 65,
  "intervention_triggered": true,
  "self_exclusion_offered": true,
  "follow_up_required": true,
  "compliance_status": "ACTIONED"
}`,
    },
    {
        method: 'GET',
        path: '/v1/gaming/iso-9001-guest-satisfaction',
        description: 'Get ISO 9001 quality metrics for hospitality operations',
        category: 'ISO Compliance',
        requiresAuth: true,
        responseExample: `{
  "standard": "ISO 9001:2015",
  "casino_location": "Vegas Main Floor",
  "guest_satisfaction": {
    "overall_score": 4.7,
    "baseline_score": 4.2,
    "improvement_percentage": 12
  },
  "service_quality_metrics": {
    "avg_response_time_minutes": 3.5,
    "complaint_resolution_rate": 96,
    "repeat_guest_percentage": 68
  },
  "operational_efficiency": {
    "process_improvements_ytd": 24,
    "staff_training_hours": 1250
  },
  "certification_status": "MAINTAINED"
}`,
    },
];

export const gamingSdkExamples: SdkExample[] = [
    {
        language: 'typescript',
        installCommand: '$ npm install @regengine/gaming-sdk',
        description: 'Type-safe SDK for gaming compliance automation',
        quickstartCode: `import { GamingCompliance } from '@regengine/gaming-sdk';

const gaming = new GamingCompliance('rge_your_api_key');

// Log casino transaction
const log = await gaming.transactionLog.create({
  transaction_id: 'TXN-20240126-001234',
  transaction_type: 'SLOT_MACHINE_PAYOUT',
  player_id: 'P-VIP-12345',
  machine_id: 'SLOT-A-042',
  amount_cents: 250000,
  casino_location: 'Vegas Main Floor',
  jurisdiction: 'Nevada'
});

console.log('✅ Transaction logged:', log.log_id);
console.log('🔒 Content hash:', log.content_hash);
console.log('📅 Retention until:', log.retention_until);`,
    },
    {
        language: 'python',
        installCommand: '$ pip install regengine-gaming',
        description: 'Python SDK for casino compliance',
        quickstartCode: `from regengine.gaming import GamingCompliance

gaming = GamingCompliance(api_key='rge_your_api_key')

# Log casino transaction
log = gaming.transaction_log.create(
    transaction_id='TXN-20240126-001234',
    transaction_type='SLOT_MACHINE_PAYOUT',
    player_id='P-VIP-12345',
    machine_id='SLOT-A-042',
    amount_cents=250000,
    casino_location='Vegas Main Floor',
    jurisdiction='Nevada'
)

print(f'✅ Transaction logged: {log.log_id}')
print(f'🔒 Content hash: {log.content_hash}')`,
    },
    {
        language: 'go',
        installCommand: '$ go get github.com/regengine/gaming-sdk-go',
        description: 'Go SDK for high-volume transaction logging',
        quickstartCode: `package main

import (
    "github.com/regengine/gaming-sdk-go"
)

func main() {
    client := gaming.NewClient("rge_your_api_key")
    
    log, err := client.TransactionLog.Create(&gaming.TransactionRequest{
        TransactionID: "TXN-20240126-001234",
        TransactionType: "SLOT_MACHINE_PAYOUT",
        PlayerID: "P-VIP-12345",
        MachineID: "SLOT-A-042",
        AmountCents: 250000,
        Jurisdiction: "Nevada",
    })
    
    if err != nil {
        panic(err)
    }
    
    fmt.Printf("Transaction logged: %s\\n", log.ID)
}`,
    },
];
