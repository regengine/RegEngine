
import unittest
from decimal import Decimal
from datetime import datetime
from services.admin.app.verticals.finance.reconciliation_bot import ReconciliationBot, TransactionRecord, InventoryLog

class TestReconciliationBot(unittest.TestCase):
    def setUp(self):
        self.bot = ReconciliationBot()
        self.base_time = datetime(2026, 1, 24, 12, 0)

    def test_perfect_reconciliation(self):
        """Test the happy path where sales match inventory."""
        transactions = [
            TransactionRecord(id="TX_1", timestamp=self.base_time, amount=Decimal("100.00"), type="sale", description="Item A"),
        ]
        logs = [
            InventoryLog(id="LOG_1", timestamp=self.base_time, sku="Item A", quantity_change=-1, unit_price=Decimal("100.00")),
        ]
        
        issues = self.bot.reconcile_sales(transactions, logs)
        self.assertEqual(len(issues), 0)

    def test_revenue_leak(self):
        """Test variance where inventory drop > sales reported (Possible theft or pricing error)."""
        transactions = [
            TransactionRecord(id="TX_1", timestamp=self.base_time, amount=Decimal("89.00"), type="sale", description="Item A Discounted?"),
        ]
        logs = [
            # Item worth 100 was sold
            InventoryLog(id="LOG_1", timestamp=self.base_time, sku="Item A", quantity_change=-1, unit_price=Decimal("100.00")),
        ]
        
        issues = self.bot.reconcile_sales(transactions, logs)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "HIGH")
        self.assertIn("Revenue Mismatch", issues[0].description)

    def test_critical_variance(self):
        """Test massive variance triggering critical alert."""
        transactions = [] # $0 sales
        logs = [
            # $2000 of inventory gone
            InventoryLog(id="LOG_1", timestamp=self.base_time, sku="Laptop", quantity_change=-1, unit_price=Decimal("2000.00")),
        ]
        
        issues = self.bot.reconcile_sales(transactions, logs)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "CRITICAL")

if __name__ == '__main__':
    unittest.main()
