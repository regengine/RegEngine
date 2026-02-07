#!/usr/bin/env node
/**
 * Seed Review Queue with Demo Hallucination Records
 * 
 * This script creates sample review items that appear in the Curator Review queue.
 * Uses realistic regulatory extraction data from DORA regulation.
 */

const fs = require('fs');
const path = require('path');

// Load admin key from .env
function getAdminKey() {
    const envPath = path.resolve(__dirname, '..', '.env');
    if (!fs.existsSync(envPath)) {
        console.error('ERROR: .env file not found at', envPath);
        process.exit(1);
    }
    const envContent = fs.readFileSync(envPath, 'utf8');
    const match = envContent.match(/ADMIN_MASTER_KEY=(.*)$/m);
    if (!match || !match[1]) {
        console.error('ERROR: ADMIN_MASTER_KEY not found in .env');
        process.exit(1);
    }
    let key = match[1].trim();
    if ((key.startsWith('"') && key.endsWith('"')) || (key.startsWith("'") && key.endsWith("'"))) {
        key = key.slice(1, -1);
    }
    return key;
}

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

// Sample hallucination records based on DORA regulation extractions
const SAMPLE_HALLUCINATIONS = [
    {
        document_id: "dora-2022-2554-art-5",
        doc_hash: "07cf835b91d23f23d6943da249a0d1f7fac11442021686fa27d51928c3c8e9ed",
        extractor: "obligation-extractor-v2",
        confidence_score: 0.73,
        extraction: {
            type: "OBLIGATION",
            entity: "Financial Entity",
            action: "shall establish and maintain resilient ICT systems",
            deadline: "24 months from entry into force",
            article: "Article 5",
            penalty: "Up to 2% of annual turnover"
        },
        text_raw: "Financial entities shall establish and maintain resilient ICT systems and tools that minimise the impact of ICT risk.",
        provenance: { page: 12, section: "Chapter II", paragraph: 1 }
    },
    {
        document_id: "dora-2022-2554-art-6",
        doc_hash: "07cf835b91d23f23d6943da249a0d1f7fac11442021686fa27d51928c3c8e9ed",
        extractor: "risk-framework-extractor-v1",
        confidence_score: 0.65,
        extraction: {
            type: "REQUIREMENT",
            entity: "ICT Risk Management Framework",
            components: ["policies", "procedures", "protocols", "tools"],
            frequency: "Annual review",
            article: "Article 6"
        },
        text_raw: "As part of the ICT risk management framework, financial entities shall use and maintain updated ICT systems, protocols and tools.",
        provenance: { page: 14, section: "Chapter II", paragraph: 3 }
    },
    {
        document_id: "dora-2022-2554-art-11",
        doc_hash: "07cf835b91d23f23d6943da249a0d1f7fac11442021686fa27d51928c3c8e9ed",
        extractor: "incident-reporting-extractor-v1",
        confidence_score: 0.58,
        extraction: {
            type: "REPORTING_OBLIGATION",
            entity: "Major ICT-related Incident",
            deadline: "4 hours for initial notification",
            authority: "Competent Authority",
            article: "Article 11",
            template_required: true
        },
        text_raw: "Financial entities shall report major ICT-related incidents to the relevant competent authority within the timeframes laid down.",
        provenance: { page: 22, section: "Chapter III", paragraph: 1 }
    },
    {
        document_id: "dora-2022-2554-art-28",
        doc_hash: "07cf835b91d23f23d6943da249a0d1f7fac11442021686fa27d51928c3c8e9ed",
        extractor: "third-party-extractor-v1",
        confidence_score: 0.71,
        extraction: {
            type: "THIRD_PARTY_REQUIREMENT",
            entity: "ICT Third-Party Service Provider",
            requirements: ["due diligence", "risk assessment", "contractual terms"],
            critical_provider_designation: "ESA oversight",
            article: "Article 28"
        },
        text_raw: "Financial entities shall adopt and regularly review a strategy on ICT third-party risk.",
        provenance: { page: 45, section: "Chapter V", paragraph: 2 }
    },
    {
        document_id: "dora-2022-2554-art-30",
        doc_hash: "07cf835b91d23f23d6943da249a0d1f7fac11442021686fa27d51928c3c8e9ed",
        extractor: "contract-clause-extractor-v1",
        confidence_score: 0.62,
        extraction: {
            type: "CONTRACT_REQUIREMENT",
            entity: "ICT Services Contract",
            mandatory_clauses: [
                "exit strategies",
                "audit rights",
                "performance metrics",
                "subcontracting rules"
            ],
            article: "Article 30"
        },
        text_raw: "Contractual arrangements on the use of ICT services shall include specific contractual provisions.",
        provenance: { page: 48, section: "Chapter V", paragraph: 5 }
    }
];

async function seedReviewQueue() {
    console.log('Seeding Review Queue with Demo Data...\n');

    const adminKey = getAdminKey();
    let success = 0;
    let failed = 0;

    // First, create a demo tenant
    console.log('1. Creating demo tenant...');
    let tenantId;
    try {
        const tenantRes = await fetch(`${ADMIN_URL}/v1/admin/tenants`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Key': adminKey
            },
            body: JSON.stringify({
                name: 'Demo Seed Tenant ' + new Date().toISOString()
            })
        });
        if (tenantRes.ok) {
            const tenantData = await tenantRes.json();
            tenantId = tenantData.tenant_id;
            console.log(`   ✓ Tenant created: ${tenantId}\n`);
        } else {
            console.error('   ✗ Failed to create tenant:', await tenantRes.text());
            process.exit(1);
        }
    } catch (err) {
        console.error('   ✗ Error creating tenant:', err.message);
        process.exit(1);
    }

    // Now seed the hallucinations with the tenant_id
    console.log('2. Creating review queue items...');
    for (const record of SAMPLE_HALLUCINATIONS) {
        // Add tenant_id to each record
        const recordWithTenant = { ...record, tenant_id: tenantId };

        try {
            const res = await fetch(`${ADMIN_URL}/v1/admin/review/hallucinations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Key': adminKey
                },
                body: JSON.stringify(recordWithTenant)
            });

            if (res.ok) {
                const data = await res.json();
                console.log(`   ✓ Created: ${record.extraction.type} (${record.extraction.article}) - Confidence: ${(record.confidence_score * 100).toFixed(0)}%`);
                success++;
            } else {
                const error = await res.text();
                console.log(`   ✗ Failed: ${record.document_id} - ${error}`);
                failed++;
            }
        } catch (err) {
            console.log(`   ✗ Error: ${record.document_id} - ${err.message}`);
            failed++;
        }
    }

    console.log(`\n--- Summary ---`);
    console.log(`Created: ${success}`);
    console.log(`Failed: ${failed}`);

    if (success > 0) {
        console.log('\n✓ Review Queue seeded! Visit http://localhost:3000/review to see the items.');
    }
}

seedReviewQueue();
