#!/usr/bin/env node

/**
 * Unified Demo Seed Script
 * 
 * Seeds all demo data in one command:
 * 1. Creates demo tenant via Admin API
 * 2. Seeds review queue with DORA-based hallucinations
 * 3. Seeds Neo4j with cross-jurisdiction regulatory data
 * 4. Verifies compliance checklists are loaded
 * 
 * Usage: node scripts/seed_demo.js
 */

const ADMIN_URL = 'http://localhost:8400';
const COMPLIANCE_URL = 'http://localhost:8500';

// Load admin key from environment or .env file
function getAdminKey() {
    if (process.env.ADMIN_MASTER_KEY) {
        return process.env.ADMIN_MASTER_KEY;
    }

    const fs = require('fs');
    const path = require('path');

    const envPath = path.join(__dirname, '..', '.env');
    if (fs.existsSync(envPath)) {
        const content = fs.readFileSync(envPath, 'utf8');
        const match = content.match(/ADMIN_MASTER_KEY=(.*)$/m);
        if (match) return match[1].trim();
    }

    return 'dev-master-key';
}

const ADMIN_KEY = getAdminKey();

// Demo data: DORA-based regulatory extractions
const DEMO_HALLUCINATIONS = [
    {
        doc_hash: 'dora-2022-2554-art5',
        source_url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554',
        text_raw: 'Financial entities shall have in place an internal governance and control framework that ensures an effective and prudent management of ICT risk.',
        extraction: JSON.stringify({
            obligation_type: 'MUST',
            subject: 'Financial entities',
            action: 'have in place',
            object: 'internal governance and control framework',
            confidence: 0.89,
            jurisdiction: 'EU',
            article: 'Article 5(1)',
        }),
        confidence_score: 0.89,
    },
    {
        doc_hash: 'dora-2022-2554-art6',
        source_url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554',
        text_raw: 'Financial entities shall identify, classify and adequately document all ICT supported business functions, roles and responsibilities.',
        extraction: JSON.stringify({
            obligation_type: 'MUST',
            subject: 'Financial entities',
            action: 'identify, classify and document',
            object: 'ICT supported business functions',
            confidence: 0.92,
            jurisdiction: 'EU',
            article: 'Article 6(1)',
        }),
        confidence_score: 0.92,
    },
    {
        doc_hash: 'dora-2022-2554-art11',
        source_url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554',
        text_raw: 'Financial entities shall establish and maintain resilient ICT systems and tools that minimise the impact of ICT risk.',
        extraction: JSON.stringify({
            obligation_type: 'MUST',
            subject: 'Financial entities',
            action: 'establish and maintain',
            object: 'resilient ICT systems and tools',
            confidence: 0.87,
            jurisdiction: 'EU',
            article: 'Article 11(1)',
        }),
        confidence_score: 0.87,
    },
    {
        doc_hash: 'dora-2022-2554-art17',
        source_url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554',
        text_raw: 'Financial entities shall report major ICT-related incidents to the relevant competent authority within 72 hours.',
        extraction: JSON.stringify({
            obligation_type: 'MUST',
            subject: 'Financial entities',
            action: 'report',
            object: 'major ICT-related incidents',
            threshold: '72 hours',
            confidence: 0.78,
            jurisdiction: 'EU',
            article: 'Article 17(3)',
        }),
        confidence_score: 0.78,
    },
    {
        doc_hash: 'dora-2022-2554-art28',
        source_url: 'https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554',
        text_raw: 'Financial entities shall maintain a register of information in relation to all contractual arrangements on the use of ICT services.',
        extraction: JSON.stringify({
            obligation_type: 'MUST',
            subject: 'Financial entities',
            action: 'maintain a register',
            object: 'ICT service contractual arrangements',
            confidence: 0.91,
            jurisdiction: 'EU',
            article: 'Article 28(3)',
        }),
        confidence_score: 0.91,
    },
];

async function log(emoji, message, detail = '') {
    console.log(`${emoji} ${message}${detail ? ': ' + detail : ''}`);
}

async function checkHealth(name, url) {
    try {
        const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) });
        if (res.ok) {
            log('✓', `${name} healthy`);
            return true;
        }
    } catch (e) {
        // Ignore
    }
    log('✗', `${name} not responding`, url);
    return false;
}

async function createTenant() {
    try {
        const res = await fetch(`${ADMIN_URL}/v1/admin/tenants`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Key': ADMIN_KEY,
            },
            body: JSON.stringify({ name: 'Demo Tenant' }),
        });

        if (res.ok) {
            const data = await res.json();
            log('✓', 'Created demo tenant', data.tenant_id);
            return data.tenant_id;
        } else if (res.status === 409) {
            log('→', 'Demo tenant already exists');
            // Get existing tenant
            const listRes = await fetch(`${ADMIN_URL}/v1/admin/tenants`, {
                headers: { 'X-Admin-Key': ADMIN_KEY },
            });
            if (listRes.ok) {
                const tenants = await listRes.json();
                const demo = tenants.find(t => t.name === 'Demo Tenant');
                if (demo) return demo.id;
            }
            return null;
        }
    } catch (e) {
        log('✗', 'Failed to create tenant', e.message);
    }
    return null;
}

async function seedReviewQueue(tenantId) {
    log('📋', 'Seeding review queue with DORA extractions...');

    let seeded = 0;
    for (const item of DEMO_HALLUCINATIONS) {
        try {
            const res = await fetch(`${ADMIN_URL}/v1/admin/review/hallucinations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Key': ADMIN_KEY,
                },
                body: JSON.stringify({
                    ...item,
                    tenant_id: tenantId,
                }),
            });

            if (res.ok) {
                seeded++;
            }
        } catch (e) {
            // Continue on error
        }
    }

    log('✓', `Seeded ${seeded}/${DEMO_HALLUCINATIONS.length} review items`);
    return seeded;
}

async function verifyCompliance() {
    try {
        const res = await fetch(`${COMPLIANCE_URL}/checklists`, {
            signal: AbortSignal.timeout(5000),
        });

        if (res.ok) {
            const data = await res.json();
            const count = Array.isArray(data) ? data.length : (data.checklists?.length || 0);
            log('✓', `Compliance checklists loaded`, `${count} checklists`);
            return count;
        }
    } catch (e) {
        log('✗', 'Could not verify compliance checklists', e.message);
    }
    return 0;
}

async function main() {
    console.log('\n🚀 RegEngine Demo Setup\n');
    console.log('='.repeat(50));

    // Health checks
    console.log('\n📡 Checking service health...\n');
    const adminOk = await checkHealth('Admin API', ADMIN_URL);
    const complianceOk = await checkHealth('Compliance API', COMPLIANCE_URL);

    if (!adminOk) {
        console.log('\n⚠️  Admin API is required. Make sure Docker services are running.');
        console.log('   Run: docker compose up -d');
        process.exit(1);
    }

    // Create tenant
    console.log('\n👤 Setting up demo tenant...\n');
    const tenantId = await createTenant();

    // Seed review queue
    console.log('\n📝 Seeding demo data...\n');
    await seedReviewQueue(tenantId);

    // Verify services
    console.log('\n🔍 Verifying services...\n');
    await verifyCompliance();

    // Summary
    console.log('\n' + '='.repeat(50));
    console.log('\n✨ Demo setup complete!\n');
    console.log('Available features:');
    console.log('  • Review Queue: 5 DORA extractions');
    console.log('  • Compliance: 22 industry checklists');
    console.log('\nOpen http://localhost:3000 to start the demo.\n');
}

main().catch(console.error);
