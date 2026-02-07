"""Command-line interface for RegEngine ingestion framework."""

import click
from datetime import datetime
from pathlib import Path

from . import create_engine_local, IngestionConfig, SourceType


@click.group()
def cli():
    """RegEngine Ingestion Framework CLI."""
    pass


@cli.command()
@click.option("--source", "-s", type=click.Choice(["federal_register", "ecfr", "fda"]), required=True)
@click.option("--vertical", "-v", required=True, help="Regulatory vertical (fsma, energy, nuclear, healthcare)")
@click.option("--max-documents", "-n", default=10, help="Maximum documents to ingest")
@click.option("--data-path", default="./data", help="Local data directory")
@click.option("--date-from", type=click.DateTime(), help="Start date (YYYY-MM-DD)")
@click.option("--agencies", multiple=True, help="Filter by agencies (can specify multiple)")
def ingest(source, vertical, max_documents, data_path, date_from, agencies):
    """Ingest regulatory documents from a source."""
    click.echo(f"🚀 Starting ingestion: {source} → {vertical}")
    click.echo(f"📁 Data path: {data_path}")
    click.echo(f"📄 Max documents: {max_documents}")
    
    # Create engine
    engine = create_engine_local(data_path=data_path)
    
    # Create config
    config = IngestionConfig(
        source_type=SourceType(source),
        vertical=vertical,
        max_documents=max_documents,
        date_from=date_from,
        source_config={"agencies": list(agencies)} if agencies else {}
    )
    
    # Run ingestion
    with click.progressbar(length=max_documents, label="Ingesting") as bar:
        result = engine.run_job(config)
        bar.update(result.job.documents_processed)
    
    # Display results
    click.echo("\n✅ Ingestion complete!")
    click.echo(f"  Job ID: {result.job.job_id}")
    click.echo(f"  Status: {result.job.status.value}")
    click.echo(f"  Processed: {result.job.documents_processed}")
    click.echo(f"  Succeeded: {result.job.documents_succeeded}")
    click.echo(f"  Failed: {result.job.documents_failed}")
    click.echo(f"  Skipped (duplicates): {result.job.documents_skipped}")
    click.echo(f"  Success rate: {result.success_rate:.1f}%")
    
    if result.errors:
        click.echo(f"\n⚠️  Errors: {len(result.errors)}")
        for error in result.errors[:5]:  # Show first 5
            click.echo(f"  - {error.get('document', 'unknown')}: {error.get('error', 'unknown')}")


@cli.command()
@click.option("--db-host", default="localhost", help="Database host")
@click.option("--db-name", default="regengine", help="Database name")
@click.option("--db-user", default="regengine", help="Database user")
@click.option("--db-password", prompt=True, hide_input=True, help="Database password")
def init_db(db_host, db_name, db_user, db_password):
    """Initialize database schema."""
    import psycopg2
    from pathlib import Path
    
    click.echo("🔧 Initializing database schema...")
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password
        )
        
        # Read migration file
        migrations_dir = Path(__file__).parent.parent.parent / "migrations"
        migration_file = migrations_dir / "V001__ingestion_schema.sql"
        
        if not migration_file.exists():
            click.echo(f"❌ Migration file not found: {migration_file}")
            return
        
        with open(migration_file) as f:
            sql = f.read()
        
        # Execute migration
        with conn.cursor() as cur:
            cur.execute(sql)
        
        conn.commit()
        conn.close()
        
        click.echo("✅ Database schema initialized successfully")
        click.echo(f"  Created schema: ingestion")
        click.echo(f"  Created tables: documents, jobs, audit_log")
        
    except Exception as e:
        click.echo(f"❌ Database initialization failed: {e}")



@cli.command()
@click.option("--vertical", "-v", help="Filter by vertical")
@click.option("--source", "-s", help="Filter by source type")
@click.option("--limit", default=10, help="Number of documents to show")
@click.option("--db-host", default="localhost")
@click.option("--db-name", default="regengine")
@click.option("--db-user", default="regengine")
@click.option("--db-password", envvar="REGENGINE_DB_PASSWORD")
def search(vertical, source, limit, db_host, db_name, db_user, db_password):
    """Search ingested documents."""
    from ..config import DatabaseConfig
    from ..storage.database import DatabaseManager
    
    click.echo(f"🔍 Searching documents...")
    
    try:
        # Create database manager
        config = DatabaseConfig(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password or ""
        )
        
        with DatabaseManager(config) as db:
            results = db.search_documents(
                vertical=vertical,
                source_type=source,
                limit=limit
            )
            
            if not results:
                click.echo("  No documents found")
                return
            
            click.echo(f"\n✅ Found {len(results)} documents:\n")
            for doc in results:
                click.echo(f"  📄 {doc['title'][:60]}...")
                click.echo(f"     ID: {doc['id']}")
                click.echo(f"     Vertical: {doc['vertical']}")
                click.echo(f"     Source: {doc['source_type']}")
                click.echo(f"     Created: {doc['created_at']}")
                click.echo()
                
    except Exception as e:
        click.echo(f"❌ Search failed: {e}")


@cli.command()
@click.argument("job-id")
@click.option("--data-path", default="./data", help="Data directory")
def status(job_id, data_path):
    """Check job status."""
    audit_file = Path(data_path) / "audit" / f"job_{job_id}.jsonl"
    
    if not audit_file.exists():
        click.echo(f"❌ Job not found: {job_id}")
        return
    
    click.echo(f"📊 Job Status: {job_id}")
    click.echo(f"  Audit log: {audit_file}")
    
    # Count audit entries
    with open(audit_file) as f:
        lines = f.readlines()
    
    click.echo(f"  Audit entries: {len(lines)}")
    click.echo("\n  Recent activity:")
    for line in lines[-5:]:  # Show last 5
        import json
        entry = json.loads(line)
        click.echo(f"    {entry['timestamp']}: {entry['action']} {entry['resource_type']} - {entry['status']}")


@cli.command()
@click.argument("document-id")
@click.option("--data-path", default="./data", help="Data directory")
@click.option("--db-host", default="localhost")
@click.option("--db-name", default="regengine")
@click.option("--db-user", default="regengine")
@click.option("--db-password", envvar="REGENGINE_DB_PASSWORD")
def verify(document_id, data_path, db_host, db_name, db_user, db_password):
    """Verify document integrity."""
    from ..config import DatabaseConfig
    from ..storage.database import DatabaseManager
    from ..storage.manager import StorageManager
    from ..utils import hash_content
    from pathlib import Path
    
    click.echo(f"🔐 Verifying document: {document_id}")
    
    try:
        # Get document from database
        config = DatabaseConfig(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password or ""
        )
        
        with DatabaseManager(config) as db:
            doc = db.get_document(document_id)
            
            if not doc:
                click.echo(f"❌ Document not found: {document_id}")
                return
            
            # Retrieve document content
            storage = StorageManager(Path(data_path))
            content = storage.retrieve_document(doc['storage_key'])
            
            # Compute hash
            computed_sha256, computed_sha512 = hash_content(content)
            
            # Verify
            sha256_match = computed_sha256 == doc['content_sha256']
            sha512_match = computed_sha512 == doc['content_sha512']
            
            click.echo(f"\n  Document: {doc['title']}")
            click.echo(f"  Storage: {doc['storage_key']}")
            click.echo(f"\n  SHA-256: {'✅ MATCH' if sha256_match else '❌ MISMATCH'}")
            click.echo(f"    Expected: {doc['content_sha256']}")
            click.echo(f"    Computed: {computed_sha256}")
            click.echo(f"\n  SHA-512: {'✅ MATCH' if sha512_match else '❌ MISMATCH'}")
            click.echo(f"    Expected: {doc['content_sha512'][:32]}...")
            click.echo(f"    Computed: {computed_sha512[:32]}...")
            
            if sha256_match and sha512_match:
                click.echo(f"\n✅ Document integrity verified")
            else:
                click.echo(f"\n❌ Document integrity FAILED - possible tampering")
                
    except Exception as e:
        click.echo(f"❌ Verification failed: {e}")


if __name__ == "__main__":
    cli()
