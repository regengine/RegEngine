"""
Billing Service — In-Memory Store

Shared state for subscriptions and checkout sessions.
In a production environment, this would be replaced by a database (Postgres/DynamoDB).
"""

from typing import Dict, Any

# Type hints for models (avoiding circular imports by using Any or string forward refs if needed)
# In a real app we'd use proper distinct models package.
subscriptions: Dict[str, Any] = {}  # tenant_id -> Subscription
sessions: Dict[str, Any] = {}       # session_id -> CheckoutSession
