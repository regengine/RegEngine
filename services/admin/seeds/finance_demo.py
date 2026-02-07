
import sys
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Mock dependencies
from services.admin.app.verticals.finance.reconciliation_bot import ReconciliationBot, TransactionRecord, InventoryLog

def run_finance_demo():
    print("💰 Starting Finance Vertical Demo...")
    print("---------------------------------------")
    
    # 1. Simulate Project Creation
    print("\n[1] Creating Finance Audit Project...")
    project_metadata = {
        "audit_standard": "sox",
        "fiscal_year_end": "2026-12-31",
        "internal_controls_framework": "COSO"
    }
    print(f"    > Project: 'Q4 SOX 404 Certification'")
    print(f"    > Metadata: {project_metadata}")
    
    # 2. Simulate Loading RulePack
    print("\n[2] Loading 'finance_pci_sox_v1' RulePack...")
    rules = ["SOX-REV-01", "SOX-AUD-01"]
    print(f"    > Activated {len(rules)} base rules.")
    
    # 3. Simulate The Interaction (Reconciliation Bot)
    print("\n[3] Running Reconciliation Bot (SOX Control 404: Revenue Accuracy)...")
    
    # Scenario: "The Midnight Discount"
    # A sale was recorded for $500, but checking inventory shows we shipped $5000 worth of goods.
    
    print("    > Fetching Transaction Logs...")
    transactions = [
        TransactionRecord(id="TX_991", timestamp=datetime.now(), amount=Decimal("500.00"), type="sale", description="Bulk Order (Special Discount)"),
    ]
    print(f"      - Transaction TX_991: $500.00")
    
    print("    > Fetching Warehouse Inventory Logs...")
    logs = [
        InventoryLog(id="INV_882", timestamp=datetime.now(), sku="SERVER-RACK-X1", quantity_change=-5, unit_price=Decimal("1000.00")),
    ]
    print(f"      - Inventory Out: 5x Server Rack @ $1000/ea = $5000.00")
    
    bot = ReconciliationBot()
    issues = bot.reconcile_sales(transactions, logs)
    
    # 4. Display Results
    if issues:
        print(f"\n🚨 SOX CONTROL FAILURE DETECTED ({len(issues)}):")
        for issue in issues:
            print(f"    [severity={issue.severity}] {issue.description}")
            print(f"    -> Action: {issue.recommended_action}")
    else:
        print("\n✅ Reconciliation Balanced.")
        
    print("\n---------------------------------------")
    print("Finance Vertical Demo Complete.")

if __name__ == "__main__":
    run_finance_demo()
