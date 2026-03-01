---
applies_to: ["."]
---

# RegEngine AI Coding Agent Instructions

> ⚠️ **Implementation Gaps ("Potemkin" List)** - Read before running the stack:
> 
> | Gap | Current State | Action Required |
> |-----|--------------|-----------------|
> | **Scrapers** | `nydfs.py` returns `b""` (empty bytes) | Implement `requests`/`BeautifulSoup` in `fetch()` |
> | **Scheduler** | No auto-ingestion trigger exists | Create `services/scheduler/` with APScheduler or cron |
> | **Compliance Service** | Code exists but missing from docker-compose | Add to stack or run via `uvicorn services.compliance.main:app --port 8500` |
> 
> The stack will "start" but produce no meaningful data without addressing these gaps.

## Architecture Overview

RegEngine is a **multi-tenant regulatory compliance platform** with an event-driven microservices architecture:

```
Ingestion → Kafka → NLP Extraction → Kafka → Neo4j Graph
                         ↓
                 (low confidence)
                         ↓
                Review Queue → Admin Service
```

**Key Services** (all FastAPI, ports 8000-8400):
- `services/ingestion/` (8000) - URL fetch, PDF→text normalization, S3 storage, Kafka emission
- `services/nlp/` (8100) - LLM/rule extraction, confidence routing to graph or review queue  
- `services/graph/` (8200) - Neo4j CRUD, Kafka consumer for GraphEvents
- `services/opportunity/` (8300) - Cypher-based regulatory arbitrage/gap queries
- `services/admin/` (8400) - API key management, HITL review, tenant overlays

**Data Flow**: Documents enter via `POST /ingest/url` → normalized to `ingest.normalized` Kafka topic → NLP extracts obligations → routes to `graph.update` (≥0.85 confidence) or `nlp.needs_review` (below threshold).

## Critical Conventions

### Shared Module Pattern
All services import from `/shared/` for auth, schemas, and security:
```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from shared.auth import require_api_key
from shared.schemas import ExtractionPayload, GraphEvent
```

### API Authentication
Every non-health endpoint requires `X-RegEngine-API-Key` header. Use `require_api_key` dependency:
```python
from shared.auth import require_api_key, verify_jurisdiction_access

@router.post("/v1/endpoint")
def handler(api_key=Depends(require_api_key)):
    verify_jurisdiction_access(api_key, "US-NY")  # Entitlement gating
```

### Pydantic Schemas (shared/schemas.py)
**Always use canonical schemas** for inter-service contracts - never ad-hoc dicts:
- `NormalizedEvent` - Ingestion→NLP
- `ExtractionPayload` - NLP extraction results
- `GraphEvent` - NLP→Graph consumer
- `ReviewItem` - Low-confidence items for HITL

### Kafka Topics
- `ingest.normalized` - Raw document metadata
- `graph.update` - High-confidence extractions for Neo4j
- `nlp.needs_review` - Low-confidence items requiring human review

## Development Workflow

### Local Stack
```bash
make up              # Start all services (requires NEO4J_PASSWORD, ADMIN_MASTER_KEY env vars)
make init-local      # Create S3 buckets on MinIO
bash scripts/init-demo-keys.sh  # Bootstrap API keys, exports to .api-keys
source .api-keys     # Load DEMO_KEY and ADMIN_KEY
```

### Testing
```bash
pytest -q services/*/tests           # Per-service tests
pytest tests/                        # Integration tests  
pytest -m security                   # Security regression suite (2,260+ tests)
```

Tests require `NEO4J_PASSWORD=test-password` set in environment (see `conftest.py`).

### Code Style
```bash
make fmt             # Black + isort formatting
```

## Scraper Interface Pattern

When implementing scrapers, follow the base class contract in `services/ingestion/app/scrapers/state_adaptors/base.py`:

```python
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class Source:
    url: str
    title: Optional[str] = None
    jurisdiction_code: Optional[str] = None  # e.g., "US-NY"

@dataclass  
class FetchedItem:
    source: Source
    content_bytes: bytes        # Raw fetched content
    content_type: Optional[str] = None  # e.g., "application/pdf", "text/html"

class StateRegistryScraper(ABC):
    @abstractmethod
    def list_sources(self) -> Iterable[Source]:
        """List available sources (RSS entries, index pages)."""
    
    @abstractmethod
    def fetch(self, source: Source) -> FetchedItem:
        """Fetch content for a given source."""
```

Scrapers must return real `content_bytes` - empty bytes will fail downstream normalization.

## Neo4j Graph Schema

The knowledge graph uses this core model:

```
(Document {doc_hash, source_url})
    ↓ CONTAINS
(Provision {content_hash, text_clean, status, tenant_id})
    ↓ HAS_OBLIGATION  
(Obligation {type: MUST|MUST_NOT|SHOULD|MAY, subject, action, object})
    ↓ APPLIES_TO
(Jurisdiction {code: "US-NY", name, scope: federal|state|municipal})
```

**Tenant isolation**: Each tenant gets a separate Neo4j database (`reg_tenant_<uuid>`) or queries are scoped by `tenant_id` property. Use `Neo4jClient.get_tenant_database_name(tenant_id)` for routing.

## Structured Logging & Audit

RegEngine uses `structlog` for audit-grade JSON logging. **Critical conventions**:

```python
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

logger = structlog.get_logger("service-name")

# Always bind correlation ID from request headers
bind_contextvars(request_id=request.headers.get("X-Request-ID"))

# Log structured events with context
logger.info("operation_completed", document_id=doc_id, confidence=0.92)

# Clear context after request to prevent leakage
clear_contextvars()
```

**Audit rules**:
- Never log raw PII - use `shared.pii_encryption` if storage is necessary
- Always include `request_id` or `correlation_id` for traceability
- Use consistent event names: `{action}_{result}` (e.g., `extraction_completed`, `auth_failed`)

## Security Modules (shared/)

The `/shared/` directory contains 55+ security modules. **Usage patterns**:

| Category | Modules | When to Use |
|----------|---------|-------------|
| Input validation | `input_validation.py`, `query_safety.py` | All user-facing endpoints |
| Auth | `jwt_auth.py`, `api_key_security.py`, `rbac.py` | Protected routes |
| Encryption | `data_encryption.py`, `pii_encryption.py` | Sensitive data storage |
| Audit | `audit_logging.py`, `security_event_logging.py` | Security-relevant actions |

Apply via decorators/middleware, not inline checks. For implementation details, refer to docstrings in `shared/security_*.py`.

## LLM Extraction Pipeline

The NLP service (`services/nlp/app/extractors/llm_extractor.py`) uses a **tiered fallback**:
1. OpenAI GPT (if `LLM_API_KEY` set and model starts with "gpt")
2. Ollama local (`OLLAMA_HOST`, defaults to `llama3:8b`)
3. Returns empty `[]` if both fail

Ollama runs via docker-compose with auto-pull init container.

## Database Configuration

Services support PostgreSQL via environment variables with SQLite fallback:
```python
# services/admin/app/database.py pattern
database_url = os.getenv("ADMIN_DATABASE_URL")  # postgresql://...
fallback = os.getenv("ADMIN_FALLBACK_SQLITE", "sqlite:///./admin.db")
```

Docker-compose injects `DATABASE_URL` and `ADMIN_DATABASE_URL` from `x-env-common`.

## Industry Plugins

Compliance checklists live in `industry_plugins/{energy,finance,gaming,healthcare,technology}/`:
```yaml
# industry_plugins/finance/compliance_checklist.yaml
checklist_id: finance-aml-kyc
requirements:
  - id: AML-001
    description: Customer due diligence
```

The compliance service (`services/compliance/`) loads and validates against these.

## Key Files to Know

| File | Purpose |
|------|---------|
| `shared/schemas.py` | Canonical Pydantic models for all inter-service communication |
| `shared/auth.py` | API key validation, rate limiting, jurisdiction entitlements |
| `services/ingestion/app/scrapers/state_adaptors/base.py` | Scraper interface contract |
| `services/graph/app/neo4j_utils.py` | Neo4j client with tenant database routing |
| `docker-compose.yml` | Local stack: postgres, redis, neo4j, kafka, ollama, services |
| `Makefile` | Developer commands (`up`, `init-local`, `fmt`, `pytest`) |
| `conftest.py` | Global pytest config, sets test env vars |

## Testing Strategy

### Unit Tests
All services follow the same testing pattern:
```bash
# Run tests for a specific service
pytest -q services/ingestion/tests
pytest -q services/nlp/tests

# Run all service tests
pytest -q services/*/tests

# Run integration tests
pytest tests/

# Run security tests (2,260+ test cases)
pytest -m security
```

### Test Requirements
- All new endpoints must have corresponding tests
- Test files should be named `test_*.py` and located in service `tests/` directory
- Use existing test fixtures from `conftest.py`
- Mock external dependencies (Kafka, Neo4j, S3) using pytest fixtures
- Security-critical code must include security marker tests: `@pytest.mark.security`

### CI/CD Integration
The `.github/workflows/ci.yml` runs:
1. Black code formatting check
2. isort import sorting check
3. Pytest unit tests for all services

Always run `make fmt` before committing to ensure formatting compliance.

## Git Workflow & Commit Conventions

### Branch Naming
- Feature branches: `feature/description`
- Bug fixes: `fix/issue-description`
- Security fixes: `security/vulnerability-description`
- Documentation: `docs/topic`

### Commit Messages
Follow conventional commits format:
```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code formatting (no functional changes)
- `refactor`: Code restructuring without behavior change
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `security`: Security-related changes

Example:
```
feat(ingestion): add PDF text extraction support

Implemented PyPDF2-based extraction for regulatory PDFs.
Includes retry logic for corrupted files.

Closes #123
```

## Task Scope Guidelines

### Ideal Tasks for AI Agents
✅ **Well-suited:**
- Implementing new endpoints following existing patterns
- Adding scrapers for new jurisdictions (following base class)
- Writing tests for existing functionality
- Updating documentation
- Refactoring code for clarity
- Adding validation logic
- Implementing CRUD operations

⚠️ **Requires Caution:**
- Changes to shared security modules
- Database schema migrations
- Kafka topic structure changes
- Neo4j graph model changes
- Authentication/authorization logic

❌ **Not Recommended:**
- Major architectural changes
- Production deployment configuration
- Secrets management
- Breaking API changes without migration plan

### When to Ask for Clarification
Always ask when:
- Requirements are ambiguous or incomplete
- Multiple valid approaches exist and trade-offs are unclear
- Changes might impact other services
- Security implications are uncertain
- Performance impact is significant

## Error Handling Patterns

### API Endpoints
```python
from fastapi import HTTPException, status

@router.post("/v1/endpoint")
async def handler(api_key=Depends(require_api_key)):
    try:
        result = await process_data()
        return {"status": "success", "data": result}
    except ValidationError as e:
        logger.error("validation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "validation_failed", "message": str(e)}
        )
    except Exception as e:
        logger.exception("unexpected_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error"}
        )
```

### Kafka Consumers
```python
import structlog

logger = structlog.get_logger(__name__)

try:
    # Process message
    process_event(event)
    logger.info("event_processed", event_id=event.id)
except ValidationError as e:
    logger.error("invalid_event", error=str(e), event_id=event.id)
    # Send to dead letter queue if configured
except Exception as e:
    logger.exception("processing_failed", event_id=event.id)
    # Re-raise to trigger retry
    raise
```

## Documentation Standards

### When to Update Documentation
- **Always** update when adding new endpoints (document in service README)
- **Always** update when changing API contracts (update schemas)
- **Always** update when modifying environment variables (update `.env.example`)
- Update `CHANGELOG.md` for user-facing changes
- Update architecture diagrams for structural changes

### Docstring Requirements
Use Google-style docstrings:
```python
def extract_obligations(text: str, confidence_threshold: float = 0.85) -> List[Obligation]:
    """Extract regulatory obligations from normalized text.
    
    Args:
        text: Normalized document text
        confidence_threshold: Minimum confidence score (0.0-1.0)
        
    Returns:
        List of Obligation objects with confidence scores
        
    Raises:
        ValueError: If text is empty or confidence_threshold invalid
        ExtractionError: If LLM service is unavailable
    """
```

## Performance Considerations

### Database Queries
- Always use connection pooling (already configured in services)
- Limit result sets with pagination
- Use database indexes for frequently queried fields
- Avoid N+1 queries - use joins or batch queries

### Kafka Messages
- Keep message payloads under 1MB
- Use message keys for partitioning
- Implement idempotent consumers (handle duplicate messages)

### Neo4j Queries
- Use parameterized Cypher queries
- Index frequently queried properties
- Limit traversal depth in graph queries
- Use `EXPLAIN` to analyze query plans

## Dependency Management

### Adding Python Dependencies
1. Add to service-specific `requirements.txt`
2. Pin versions: `package==1.2.3`
3. Update service Dockerfile if needed
4. Test in isolation before committing

### Security Scanning
All dependencies are scanned via GitHub Dependabot. Never:
- Add dependencies with known vulnerabilities
- Use deprecated packages
- Add unnecessary transitive dependencies

### Common Dependencies
Already available in all services:
- `fastapi` - Web framework
- `pydantic` - Data validation
- `structlog` - Logging
- `pytest` - Testing

## Code Review Expectations

### Self-Review Checklist
Before requesting review:
- [ ] All tests pass locally (`pytest -q services/*/tests`)
- [ ] Code is formatted (`make fmt`)
- [ ] No secrets or credentials in code
- [ ] Documentation updated if needed
- [ ] Error handling is comprehensive
- [ ] Logging statements are structured
- [ ] Security implications considered

### Review Criteria
Reviewers will check:
- Code follows existing patterns
- Tests adequately cover changes
- No security vulnerabilities introduced
- Performance impact is acceptable
- Documentation is clear and accurate
