import sys
import os
import asyncio

sys.path.append(os.getcwd())

from app.analysis import AnalysisEngine

async def test_phi():
    engine = AnalysisEngine()
    result = await engine.analyze_document("test_phi_16")
    
    print(f"Document ID: {result.document_id}")
    print(f"Risk Score: {result.risk_score}")
    print(f"Risks: {[r.id for r in result.critical_risks]}")
    
    if result.risk_score == 95 and "PHI-001" in [r.id for r in result.critical_risks]:
        print("SUCCESS: PHI Detected")
    else:
        print("FAILURE: PHI Not Detected")

if __name__ == "__main__":
    asyncio.run(test_phi())
