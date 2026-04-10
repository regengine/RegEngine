#!/usr/bin/env python3
"""
RegEngine Tenant Management CLI (regctl)

Command-line tool for managing RegEngine tenants, provisioning infrastructure,
and deploying demo environments.

Usage:
  # Create a new tenant
  python scripts/regctl/tenant.py create "Demo Company" --demo-mode

  # Create with specific framework
  python scripts/regctl/tenant.py create "FinTech Corp" --demo-mode --framework soc2

  # List all tenants
  python scripts/regctl/tenant.py list

  # Delete a tenant
  python scripts/regctl/tenant.py delete <tenant-id>

  # Reset a tenant (delete and recreate with demo data)
  python scripts/regctl/tenant.py reset <tenant-id>
"""

import click
import re
import sys
import os
from pathlib import Path
from uuid import uuid4, UUID
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich import box
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.graph.app.neo4j_utils import Neo4jClient

# Allowlist: only alphanumeric + underscore allowed in schema/database names.
# Prevents SQL/Cypher injection when names are interpolated into DDL statements.
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z0-9_]+$')


def _validate_identifier(name: str, label: str = "identifier") -> str:
    """Validate that a schema or database name contains only safe characters."""
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {label}: {name!r} — only alphanumeric and underscore allowed")
    return name


class TenantManager:
    """Manages tenant provisioning and lifecycle."""

    def __init__(self):
        """Initialize tenant manager."""
        self.tenants_db_file = str(REPO_ROOT / ".tenants.db")

    def create_tenant(
        self,
        name: str,
        demo_mode: bool = False,
        framework: str = "nist"
    ) -> dict:
        """
        Create a new tenant with complete infrastructure.

        Args:
            name: Tenant name
            demo_mode: Whether to load demo data
            framework: Control framework for demo data (nist, soc2, iso27001)

        Returns:
            dict with tenant_id, name, api_key, database info
        """
        tenant_id = uuid4()

        click.echo(f"\n🚀 Creating tenant: {name}")
        click.echo(f"   Tenant ID: {tenant_id}")

        # Step 1: Create PostgreSQL schema
        click.echo("   [1/5] Creating PostgreSQL schema...")
        self._create_postgres_schema(tenant_id)
        click.echo("         ✓ Schema created")

        # Step 2: Create Neo4j database
        click.echo("   [2/5] Creating Neo4j tenant database...")
        self._create_neo4j_database(tenant_id)
        click.echo("         ✓ Neo4j database created")

        # Step 3: Generate API key
        click.echo("   [3/5] Generating API key...")
        api_key = self._generate_api_key(tenant_id, name)
        click.echo(f"         ✓ API key generated")

        # Step 4: Load demo data (if requested)
        if demo_mode:
            click.echo(f"   [4/5] Loading demo data ({framework.upper()} framework)...")
            self._load_demo_data(tenant_id, framework)
            click.echo("         ✓ Demo data loaded")
        else:
            click.echo("   [4/5] Skipping demo data (not requested)")

        # Step 5: Save tenant record
        click.echo("   [5/5] Saving tenant record...")
        self._save_tenant_record(tenant_id, name, api_key)
        click.echo("         ✓ Tenant record saved")

        click.echo(f"\n✅ Tenant created successfully!")
        click.echo(f"\n{'='*60}")
        click.echo(f"Tenant Details")
        click.echo(f"{'='*60}")
        click.echo(f"Name:       {name}")
        click.echo(f"Tenant ID:  {tenant_id}")
        click.echo(f"API Key:    {api_key}")
        click.echo(f"Framework:  {framework.upper() if demo_mode else 'N/A'}")
        click.echo(f"{'='*60}")

        if demo_mode:
            click.echo(f"\n🎯 Next Steps:")
            click.echo(f"1. Test API: curl -H 'X-RegEngine-API-Key: {api_key}' http://localhost:8000/overlay/controls")
            click.echo(f"2. View dashboard: http://localhost:3000/dashboard?tenant={tenant_id}")
            click.echo(f"3. Explore docs: http://localhost:8000/docs")

        return {
            "tenant_id": str(tenant_id),
            "name": name,
            "api_key": api_key,
            "demo_mode": demo_mode,
            "framework": framework if demo_mode else None,
        }

    def list_tenants(self):
        """List all tenants."""
        console = Console()
        
        if not os.path.exists(self.tenants_db_file):
            console.print("[yellow]No tenants found.[/yellow]")
            return []

        with open(self.tenants_db_file, 'r') as f:
            import json
            tenants = [json.loads(line) for line in f if line.strip()]

        if not tenants:
            console.print("[yellow]No tenants found.[/yellow]")
            return []

        table = Table(title="RegEngine Tenants", box=box.ROUNDED)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Tenant ID", style="green")
        table.add_column("API Key", style="magenta")
        table.add_column("Created At", style="blue")

        for tenant in tenants:
            # Format date nicely
            try:
                created_dt = datetime.fromisoformat(tenant['created_at'])
                created_str = created_dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, KeyError):
                created_str = tenant.get('created_at', 'N/A')

            table.add_row(
                tenant['name'],
                tenant['tenant_id'],
                tenant['api_key'],
                created_str
            )

        console.print(table)
        console.print(f"[dim]Total: {len(tenants)} tenant(s)[/dim]")
        return tenants

    def delete_tenant(self, tenant_id: UUID):
        """
        Delete a tenant and all associated data.

        Args:
            tenant_id: Tenant UUID to delete
        """
        click.echo(f"\n🗑️  Deleting tenant: {tenant_id}")

        # Step 1: Delete Neo4j database
        click.echo("   [1/3] Deleting Neo4j database...")
        self._delete_neo4j_database(tenant_id)
        click.echo("         ✓ Neo4j database deleted")

        # Step 2: Delete PostgreSQL schema
        click.echo("   [2/3] Deleting PostgreSQL schema...")
        self._delete_postgres_schema(tenant_id)
        click.echo("         ✓ PostgreSQL schema deleted")

        # Step 3: Remove tenant record
        click.echo("   [3/3] Removing tenant record...")
        self._remove_tenant_record(tenant_id)
        click.echo("         ✓ Tenant record removed")

        click.echo(f"\n✅ Tenant deleted successfully!")

    def reset_tenant(self, tenant_id: UUID, framework: str = "nist"):
        """
        Reset a tenant by deleting and recreating with demo data.

        Args:
            tenant_id: Tenant UUID to reset
            framework: Control framework for new demo data
        """
        # Get tenant info before deletion
        tenant_info = self._get_tenant_info(tenant_id)
        if not tenant_info:
            click.echo(f"❌ Tenant not found: {tenant_id}")
            return

        name = tenant_info['name']

        click.echo(f"\n🔄 Resetting tenant: {name}")

        # Delete existing tenant
        self.delete_tenant(tenant_id)

        # Recreate with demo data
        click.echo(f"\n🚀 Recreating tenant with demo data...")
        self.create_tenant(name, demo_mode=True, framework=framework)

    # Internal helper methods

    def _create_postgres_schema(self, tenant_id: UUID):
        """Create PostgreSQL schema for tenant."""
        from sqlalchemy import create_engine, text
        import os

        database_url = os.getenv("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")

        try:
            engine = create_engine(database_url, pool_pre_ping=True)
            schema_name = _validate_identifier(
                f"tenant_{str(tenant_id).replace('-', '_')}", "schema name"
            )

            with engine.connect() as conn:
                # Create schema
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
                conn.commit()

                # Grant permissions to regengine user
                conn.execute(text(f'GRANT ALL ON SCHEMA "{schema_name}" TO regengine'))
                conn.commit()

            engine.dispose()
        except Exception as e:
            click.echo(f"         ⚠️  Schema creation warning: {str(e)[:100]}...")
            # Don't fail - allow graceful degradation for demo purposes

    def _create_neo4j_database(self, tenant_id: UUID):
        """Create Neo4j database for tenant."""
        try:
            db_name = _validate_identifier(
                f"reg_tenant_{tenant_id}".replace('-', '_'), "Neo4j database name"
            )

            # Note: This requires Neo4j Enterprise and admin access
            # In demo mode, this may fail - that's okay
            try:
                client = Neo4jClient(database="system")
                client.execute_query(f"CREATE DATABASE `{db_name}` IF NOT EXISTS")
            except Exception as e:
                # Neo4j may not support multi-database in Community Edition
                click.echo(f"         ⚠️  Note: {str(e)[:50]}... (continuing)")
        except Exception as e:
            click.echo(f"         ⚠️  Could not create Neo4j database: {str(e)[:50]}...")

    def _generate_api_key(self, tenant_id: UUID, name: str) -> str:
        """Generate API key for tenant."""
        import hashlib
        import secrets

        # Generate a secure random key
        random_bytes = secrets.token_bytes(32)
        key_hash = hashlib.sha256(random_bytes).hexdigest()

        # Format as API key
        api_key = f"sk_live_{key_hash[:32]}"

        return api_key

    def _load_demo_data(self, tenant_id: UUID, framework: str):
        """Load demo data for tenant."""
        # Call the demo data loader script
        import subprocess

        try:
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/demo/load_demo_data.py"),
                    "--tenant-id", str(tenant_id),
                    "--framework", framework,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            click.echo(f"         ⚠️  Demo data loading had warnings: {e.stderr[:100]}")
        except FileNotFoundError:
            click.echo("         ⚠️  Demo data loader not found (continuing)")

    def _save_tenant_record(self, tenant_id: UUID, name: str, api_key: str):
        """Save tenant record to local database."""
        import json

        record = {
            "tenant_id": str(tenant_id),
            "name": name,
            "api_key": api_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Append to tenants database file
        with open(self.tenants_db_file, 'a') as f:
            f.write(json.dumps(record) + '\n')

    def _delete_neo4j_database(self, tenant_id: UUID):
        """Delete Neo4j database for tenant."""
        try:
            db_name = _validate_identifier(
                f"reg_tenant_{tenant_id}".replace('-', '_'), "Neo4j database name"
            )

            # Note: This requires Neo4j Enterprise
            try:
                client = Neo4jClient(database="system")
                client.execute_query(f"DROP DATABASE `{db_name}` IF EXISTS")
            except Exception:
                pass  # Database may not exist
        except Exception:
            pass  # Ignore errors for demo purposes

    def _delete_postgres_schema(self, tenant_id: UUID):
        """Delete PostgreSQL schema for tenant."""
        from sqlalchemy import create_engine, text
        import os

        database_url = os.getenv("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")

        try:
            engine = create_engine(database_url, pool_pre_ping=True)
            schema_name = _validate_identifier(
                f"tenant_{str(tenant_id).replace('-', '_')}", "schema name"
            )

            with engine.connect() as conn:
                # Drop schema and all objects in it
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
                conn.commit()

            engine.dispose()
        except Exception as e:
            click.echo(f"         ⚠️  Schema deletion warning: {str(e)[:100]}...")
            # Don't fail - best effort cleanup

    def _remove_tenant_record(self, tenant_id: UUID):
        """Remove tenant from local database."""
        import json

        if not os.path.exists(self.tenants_db_file):
            return

        # Read all tenants
        with open(self.tenants_db_file, 'r') as f:
            tenants = [json.loads(line) for line in f if line.strip()]

        # Filter out the deleted tenant
        tenants = [t for t in tenants if t['tenant_id'] != str(tenant_id)]

        # Rewrite file
        with open(self.tenants_db_file, 'w') as f:
            for tenant in tenants:
                f.write(json.dumps(tenant) + '\n')

    def _get_tenant_info(self, tenant_id: UUID) -> Optional[dict]:
        """Get tenant information."""
        import json

        if not os.path.exists(self.tenants_db_file):
            return None

        with open(self.tenants_db_file, 'r') as f:
            tenants = [json.loads(line) for line in f if line.strip()]

        for tenant in tenants:
            if tenant['tenant_id'] == str(tenant_id):
                return tenant

        return None


# CLI Commands

@click.group()
def tenant():
    """RegEngine tenant management commands."""
    pass


@tenant.command()
@click.argument('name')
@click.option('--demo-mode', is_flag=True, help='Load demo data')
@click.option(
    '--framework',
    type=click.Choice(['nist', 'soc2', 'iso27001']),
    default='nist',
    help='Control framework for demo data'
)
def create(name: str, demo_mode: bool, framework: str):
    """Create a new tenant."""
    manager = TenantManager()
    manager.create_tenant(name, demo_mode, framework)


@tenant.command()
def list():
    """List all tenants."""
    manager = TenantManager()
    manager.list_tenants()


@tenant.command()
@click.argument('tenant_id')
@click.confirmation_option(prompt='Are you sure you want to delete this tenant?')
def delete(tenant_id: str):
    """Delete a tenant."""
    try:
        tid = UUID(tenant_id)
    except ValueError:
        click.echo(f"❌ Invalid tenant ID: {tenant_id}")
        return

    manager = TenantManager()
    manager.delete_tenant(tid)


@tenant.command()
@click.argument('tenant_id')
@click.option(
    '--framework',
    type=click.Choice(['nist', 'soc2', 'iso27001']),
    default='nist',
    help='Control framework for new demo data'
)
def reset(tenant_id: str, framework: str):
    """Reset a tenant (delete and recreate with demo data)."""
    try:
        tid = UUID(tenant_id)
    except ValueError:
        click.echo(f"❌ Invalid tenant ID: {tenant_id}")
        return

    manager = TenantManager()
    manager.reset_tenant(tid, framework)


if __name__ == '__main__':
    tenant()
