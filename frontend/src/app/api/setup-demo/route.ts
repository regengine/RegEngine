import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function POST() {
    let adminKey = process.env.ADMIN_MASTER_KEY;

    // Fallback: Try to read from root .env file (for local dev with docker-compose)
    if (!adminKey) {
        try {
            const envPath = path.resolve(process.cwd(), '../.env');
            if (fs.existsSync(envPath)) {
                const envContent = fs.readFileSync(envPath, 'utf8');
                const match = envContent.match(/ADMIN_MASTER_KEY=(.*)$/m);
                if (match && match[1]) {
                    adminKey = match[1].trim();
                    // Remove potential quotes
                    if ((adminKey.startsWith('"') && adminKey.endsWith('"')) ||
                        (adminKey.startsWith("'") && adminKey.endsWith("'"))) {
                        adminKey = adminKey.slice(1, -1);
                    }
                }
            }
        } catch (e) {
            console.warn('Failed to read root .env file:', e);
        }
    }

    if (!adminKey) {
        return NextResponse.json(
            { error: 'Admin Master Key not configured on server' },
            { status: 500 }
        );
    }

    const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

    try {
        // 1. Create a Demo Tenant
        const tenantRes = await fetch(`${ADMIN_URL}/v1/admin/tenants`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Key': adminKey,
            },
            body: JSON.stringify({
                name: 'Demo User ' + new Date().toISOString(),
            }),
        });

        if (!tenantRes.ok) {
            throw new Error(`Failed to create tenant: ${tenantRes.statusText}`);
        }

        const tenantData = await tenantRes.json();
        const tenantId = tenantData.tenant_id;

        // 2. Create an API Key for that Tenant
        const keyRes = await fetch(`${ADMIN_URL}/v1/admin/keys`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Key': adminKey,
            },
            body: JSON.stringify({
                name: 'Demo Key',
                description: 'Auto-generated for home page demo',
                tenant_id: tenantId,
            }),
        });

        if (!keyRes.ok) {
            throw new Error(`Failed to create key: ${keyRes.statusText}`);
        }

        const keyData = await keyRes.json();

        return NextResponse.json({
            apiKey: keyData.api_key,
            tenantId: tenantId,
        });

    } catch (error: unknown) {
        console.error('Demo setup failed:', error);
        const message = error instanceof Error ? error.message : 'Failed to setup demo';
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
