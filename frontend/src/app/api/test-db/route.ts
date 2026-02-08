import { NextRequest, NextResponse } from 'next/server';
import pg from 'pg';

const { Client } = pg;

export async function GET(request: NextRequest) {
    const client = new Client({
        host: 'localhost',
        port: 5432,
        database: 'regengine_admin',
        user: 'regengine',
        password: 'regengine',
    });

    try {
        await client.connect();

        // Check what we can see
        const schemas = await client.query(`
      SELECT nspname 
      FROM pg_namespace 
      WHERE nspname NOT LIKE 'pg_%' AND nspname != 'information_schema'
      ORDER BY nspname
    `);

        const energyCheck = await client.query(`
      SELECT tablename 
      FROM pg_tables 
      WHERE schemaname = 'energy'
    `);

        // Try a direct insert to test write permissions
        let writeTest = 'not attempted';
        try {
            await client.query('BEGIN');
            await client.query(`
        INSERT INTO energy.compliance_snapshots (
          substation_id, facility_name, snapshot_time,
          system_status, asset_states, esp_config, patch_metrics,
          generated_by, content_hash
        ) VALUES (
          'TEST',  'Test', NOW(),
          'NOMINAL'::energy.system_status_enum, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
          'SYSTEM_AUTO'::energy.snapshot_generator_enum, 'test123'
        ) RETURNING id
      `);
            await client.query('ROLLBACK');
            writeTest = 'SUCCESS (rolled back)';
        } catch (e: unknown) {
            await client.query('ROLLBACK');
            const msg = e instanceof Error ? e.message : String(e);
            writeTest = `FAILED: ${msg}`;
        }

        return NextResponse.json({
            connection: 'SUCCESS',
            database: 'regengine_admin',
            schemas: schemas.rows.map(r => r.nspname),
            energy_tables: energyCheck.rows.map(r => r.tablename),
            write_test: writeTest,
        });

    } catch (error: unknown) {
        const msg = error instanceof Error ? error.message : String(error);
        const code = (error as Record<string, unknown>)?.code;
        return NextResponse.json(
            { error: msg, code },
            { status: 500 }
        );
    } finally {
        await client.end();
    }
}
