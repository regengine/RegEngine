# RegEngine Gaming Compliance Service

Immutable transaction logs and responsible gaming monitoring for casino regulatory compliance.

## 🎰 Regulatory Standards

- **Nevada Gaming Control Board** - Regulation 5 (Self-Exclusion), Regulation 6 (Transaction Logging)
- **New Jersey Division of Gaming Enforcement** - Technical Standards
- **IGRA** (Indian Gaming Regulatory Act)
- **FinCEN** - Anti-Money Laundering (AML) requirements

## 🚀 Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GAMING_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/regengine_gaming"
export GAMING_PORT=8007

# Run migrations
# (Manual for now - will integrate with Flyway/Alembic)

# Start service
python -m app.main
```

### Docker

```bash
# Build image
docker build -t regengine/gaming:latest .

# Run container
docker run -p 8007:8007 \
  -e GAMING_DATABASE_URL="postgresql://postgres:postgres@host.docker.internal:5432/regengine_gaming" \
  regengine/gaming:latest
```

## 📡 API Endpoints

### Transaction Vault

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/gaming/transaction-log` | POST | Create immutable transaction record |
| `/v1/gaming/transaction-log/{id}` | GET | Retrieve transaction with integrity verification |
| `/v1/gaming/compliance-export` | POST | Export compliance report for audits |

### Responsible Gaming

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/gaming/self-exclusion` | POST | Register player self-exclusion |
| `/v1/gaming/dashboard` | GET | Dashboard metrics |

## 🔒 Security

- **API Key Authentication**: Required via `X-RegEngine-API-Key` header
- **Immutability**: All transactions use SHA-256 content hashing
- **Idempotency**: Duplicate transaction prevention via content hash uniqueness

## 📊 Database Schema

### `transaction_logs`
Immutable transaction records with cryptographic integrity.

**Key Fields:**
- `player_id` - Player identifier
- `transaction_type` - WAGER | PAYOUT | JACKPOT | DEPOSIT | WITHDRAWAL
- `amount_cents` - Amount in cents (avoids float precision issues)
- `content_hash` - SHA-256 hash for immutability verification
- `jurisdiction` - Gaming jurisdiction (NEVADA, NEW_JERSEY, TRIBAL)

### `self_exclusion_records`
Player self-exclusion for responsible gaming.

**Key Fields:**
- `player_id` - Unique player identifier
- `duration_days` - Exclusion duration (0 = permanent)
- `status` - ACTIVE | EXPIRED | REVOKED

### `responsible_gaming_alerts`
Automated problem gambling detection.

**Key Fields:**
- `risk_score` - 0-100 behavioral risk score
- `alert_type` - HIGH_FREQUENCY | LOSS_CHASING | AFTER_HOURS
- `detection_data` - JSON metrics that triggered alert

## 🧪 Testing

```bash
# Run unit tests
pytest tests/

# Run integration tests (requires database)
pytest tests/integration/
```

## 🔄 Roadmap

**Current Status**: Phase 1 Complete (Backend buildout)

**Next Steps**:
1. **Phase 2**: Problem gambling detection graph (Neo4j integration)
2. **Phase 3**: Frontend dashboard (`/verticals/gaming/dashboard/`)
3. **Phase 4**: Surveillance timeline integration

## 📝 Compliance Notes

### Transaction Retention
- **Minimum**: 5 years (per most jurisdictions)
- **Current**: No auto-deletion (manual archival required)

### Self-Exclusion Enforcement
- Service checks self-exclusion status on every transaction
- Returns HTTP 403 if player is excluded
- Frontend must also enforce (defense-in-depth)

### AML Requirements
- All transactions logged with timestamp and amount
- Export endpoint supports date range queries for FinCEN reporting
- Jurisdiction-specific metadata stored in `metadata` JSONB field

## 🛠️ Architecture

```
┌─────────────────┐
│  Frontend       │
│  Dashboard      │
└────────┬────────┘
         │
         │ HTTP/REST
         │
┌────────▼────────┐      ┌──────────────┐
│  Gaming API     │◄─────┤  PostgreSQL  │
│  (FastAPI)      │      │  (Immutable) │
└─────────────────┘      └──────────────┘
         │
         │ (Future: Neo4j for player activity graph)
         │
┌────────▼────────┐
│  Graph Service  │
│  (Player Graph) │
└─────────────────┘
```

## 📚 Related Documentation

- [Vertical Equality Audit](../../../.gemini/antigravity/brain/efd6355a-7c66-41ce-b4ef-1eee328fe32e/vertical_representation_equality_audit.md)
- [Implementation Plan](../../../.gemini/antigravity/brain/efd6355a-7c66-41ce-b4ef-1eee328fe32e/vertical_equality_implementation_plan.md)

## 💡 Example Usage

### Create Transaction

```bash
curl -X POST http://localhost:8007/v1/gaming/transaction-log \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "P123456",
    "transaction_type": "WAGER",
    "amount_cents": 50000,
    "game_id": "SLOT_001",
    "jurisdiction": "NEVADA",
    "timestamp": "2026-01-28T20:00:00Z"
  }'
```

### Register Self-Exclusion

```bash
curl -X POST http://localhost:8007/v1/gaming/self-exclusion \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "P123456",
    "duration_days": 90,
    "reason": "Voluntary self-exclusion"
  }'
```

## 🤝 Contributing

This service follows the RegEngine vertical equality standard. All changes must maintain:
- ≥85% equality score vs. FSMA baseline
- Cryptographic immutability for compliance records
- Comprehensive API documentation
- Unit test coverage ≥80%
