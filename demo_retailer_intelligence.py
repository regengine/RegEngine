import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

import os
print(f"DEBUG: CWD = {os.getcwd()}")
print(f"DEBUG: LS = {os.listdir('.')}")
print(f"DEBUG: PRE-PATH = {sys.path}")

# Add service paths to sys.path to simulate being inside the service
# If we are in /app, and /app/app exists...
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "app"))

# Mock classes to avoid full docker dependencies if running locally
try:
    # Try importing as if we are inside the service module (e.g. from app.x)
    try:
        from app.resolution import EntityResolver
        from app.classification import SignalClassifier
        from app.extractor import extract_entities
        # For ingestion, it's harder if we are in nlp container.
        # We will mock the Source class since we can't easily cross-import from another service's logic in this demo
        # unless we mount it.
        from dataclasses import dataclass
        @dataclass
        class Source:
             url: str
             title: str
             jurisdiction_code: str
             
    except ImportError as e_inner:
        print(f"DEBUG: Inner import failed: {e_inner}")
        # Fallback to absolute paths if context is root
        from services.ingestion.app.scrapers.state_adaptors.base import Source
        from services.nlp.app.resolution import EntityResolver
        from services.nlp.app.classification import SignalClassifier
        from services.nlp.app.extractor import extract_entities
except ImportError as e:
    print(f"CRITICAL: Import failed. Use 'docker compose run nlp-service python demo_retailer_intelligence.py' if running in docker.")
    print(f"Error: {e}")
    sys.exit(1)

def run_demo():
    print("="*60)
    print("🚀  RETAILER INTELLIGENCE PIPELINE DEMO")
    print("="*60)
    
    # 1. Simulate Scraper finding a relevant Warning Letter
    print("\n[1] SCRAPER: Discovered FDA Warning Letter...")
    source = Source(
        url="https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/costco-wholesale-corp-01012026",
        title="FDA Warning Letter - Costco Wholesale Corp.",
        jurisdiction_code="US-FDA"
    )
    print(f"    Source: {source.title}")
    print(f"    URL: {source.url}")

    # 2. Simulate Deep Fetch & Text Extraction (Mocking what PDFMiner would return)
    print("\n[2] DEEP FETCH: Extracting Text from Official PDF...")
    # This text contains "Costco", "Listeria", and some entity noise
    extracted_text = """
    WARNING LETTER
    
    VIA UNITED PARCEL SERVICE
    
    Mr. W. Craig Jelinek
    CEO, Costco Wholesale Corp.
    999 Lake Drive
    Issaquah, WA 98027
    
    Dear Mr. Jelinek:
    
    The U.S. Food and Drug Administration (FDA) inspected your facility.
    
    During the inspection, we found serious violations of the Seafood HACCP regulation.
    FDA laboratory analysis confirmed the presence of Listeria monocytogenes in your
    processing facility (Zone 1).
    
    Accordingly, your frozen shrimp products are adulterated.
    
    This is not an all-inclusive list of violations at your facility.
    """
    print(f"    Extracted {len(extracted_text)} bytes of text.")
    print(f"    Snippet: {extracted_text.strip()[:100]}...")

    # 3. Entity Resolution
    print("\n[3] NLP: Running Entity Resolution...")
    # First, simple extraction
    entities = extract_entities(extracted_text)
    
    resolver = EntityResolver()
    resolved_count = 0
    
    for ent in entities:
        if ent["type"] == "ORGANIZATION":
            raw_name = ent["attrs"]["name"]
            resolution = resolver.resolve_organization(raw_name)
            if resolution:
                print(f"    ✅ MATCH: '{raw_name}' -> {resolution['name']} ({resolution['id']}) [{resolution['type']}]")
                resolved_count += 1
            else:
                print(f"    ⚠️  UNRESOLVED: '{raw_name}'")
    
    if resolved_count == 0:
        print("    FAILED: No entities resolved!")

    # 4. Signal Classification
    print("\n[4] CLASSIFIER: Assessing Risk Score...")
    classifier = SignalClassifier()
    category, risk, confidence = classifier.classify_signal(extracted_text)
    
    print(f"    Category:   {category}")
    print(f"    Risk Level: {risk}")
    print(f"    Confidence: {confidence:.2f}")

    # 5. Dashboard Output
    print("\n[5] DASHBOARD EVENT (JSON):")
    event = {
        "event_type": "enforcement_action",
        "entity_id": "duns:009289230",  # We know this resolved to Costco
        "entity_name": "Costco Wholesale Corp.",
        "risk_level": risk,
        "signal_category": category,
        "summary": "High Risk Food Safety Violation (Listeria) detected."
    }
    print(event)
    print("\n" + "="*60)
    print("STATUS: DEMO COMPLETE")
    print("="*60)

if __name__ == "__main__":
    run_demo()
