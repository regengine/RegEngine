"""Simple test of ingestion framework."""

from datetime import datetime
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from regengine_ingestion import create_engine_local, SourceType, IngestionConfig


def test_basic_ingestion():
    """Test basic ingestion workflow."""
    print("🧪 Testing RegEngine Ingestion Framework\n")
    
    # Create engine
    data_path = Path(__file__).parent.parent / "test_data"
    print(f"📁 Data path: {data_path}")
    
    engine = create_engine_local(data_path=str(data_path))
    print("✅ Engine created\n")
    
    # Configure ingestion
    config = IngestionConfig(
        source_type=SourceType.FEDERAL_REGISTER,
        vertical="fsma",
        max_documents=3,  # Just 3 for testing
        date_from=datetime(2024, 1, 1),
        source_config={"agencies": ["FDA"]}
    )
    print(f"⚙️  Config: {config.source_type.value} → {config.vertical}")
    print(f"📄 Max documents: {config.max_documents}\n")
    
    # Run ingestion
    print("🚀 Starting ingestion...")
    result = engine.run_job(config)
    
    # Display results
    print("\n" + "="*60)
    print("📊 RESULTS")
    print("="*60)
    print(f"Job ID: {result.job.job_id}")
    print(f"Status: {result.job.status.value}")
    print(f"Processed: {result.job.documents_processed}")
    print(f"Succeeded: {result.job.documents_succeeded}")
    print(f"Failed: {result.job.documents_failed}")
    print(f"Skipped: {result.job.documents_skipped}")
    print(f"Success Rate: {result.success_rate:.1f}%")
    
    if result.documents:
        print(f"\n✅ Sample documents ({len(result.documents)}):")
        for doc in result.documents[:3]:
            print(f"\n  📄 {doc.title[:60]}...")
            print(f"     ID: {doc.id}")
            print(f"     Hash: {doc.hash.content_sha256[:16]}...")
            print(f"     Type: {doc.document_type.value}")
            print(f"     Text length: {doc.text_length:,} chars")
    
    if result.errors:
        print(f"\n⚠️  Errors ({len(result.errors)}):")
        for error in result.errors[:3]:
            print(f"  - {error}")
    
    # Check audit trail
    audit_file = data_path / "audit" / f"job_{result.job.job_id}.jsonl"
    if audit_file.exists():
        with open(audit_file) as f:
            audit_lines = f.readlines()
        print(f"\n📋 Audit trail: {len(audit_lines)} entries")
        print(f"   {audit_file}")
    
    print("\n" + "="*60)
    print("✅ TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    test_basic_ingestion()
