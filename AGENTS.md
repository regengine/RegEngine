# Agent Guidelines for RegEngine

This document provides guidance for AI coding agents (like GitHub Copilot) working on the RegEngine codebase.

## 🎯 Core Principles

### 1. Security First
RegEngine is a compliance platform handling sensitive regulatory data. **Every change must prioritize security:**
- Never log PII or sensitive data
- Always validate user inputs
- Use parameterized queries (SQL, Cypher)
- Apply rate limiting to public endpoints
- Encrypt sensitive data at rest
- Use existing security modules from `/shared/`

### 2. Test-Driven Development
- Write tests before or alongside implementation
- Aim for >80% code coverage on new code
- Include edge cases and error scenarios
- Use security markers for security-critical tests: `@pytest.mark.security`

### 3. Follow Existing Patterns
RegEngine has established patterns. Don't reinvent:
- Use `shared.schemas` for data contracts
- Follow the scraper base class pattern
- Use structured logging (structlog)
- Apply consistent error handling
- Use FastAPI dependency injection for auth

## 🤖 Agent Behavior Guidelines

### Ask Clarifying Questions
**Before implementing**, ask if:
- Requirements are ambiguous
- Multiple approaches exist with unclear trade-offs
- Changes might affect other services
- You're unsure about security implications
- Performance impact could be significant

**Example questions:**
- "Should this endpoint support pagination? What's the expected max result set?"
- "This scraper could use BeautifulSoup or Selenium. Which fits the project's approach?"
- "Should validation errors return 400 or 422 status codes?"

### Express Confidence Levels
Be explicit about uncertainty:
- ✅ "I'm confident this follows the established pattern for API authentication"
- ⚠️ "This should work, but I recommend load testing since it processes large files"
- ❌ "I'm uncertain about the Neo4j query performance at scale - needs review"

### When to Request Human Review
Immediately flag for human review:
- Security-critical code (auth, encryption, input validation)
- Database schema changes
- Breaking API changes
- Performance-critical code paths
- Changes to deployment configuration
- Modifications to Kafka topic structures

## 📋 Development Workflow

### Step 1: Understand the Task
1. Read the issue description carefully
2. Review related code and tests
3. Check for existing similar implementations
4. Identify affected services

### Step 2: Plan Minimal Changes
- Make the smallest possible change to achieve the goal
- Avoid refactoring unrelated code
- Preserve existing behavior
- Update only necessary tests

### Step 3: Implement with Tests
```bash
# 1. Create or update tests first
vi services/ingestion/tests/test_new_feature.py

# 2. Implement the feature
vi services/ingestion/app/endpoints.py

# 3. Run tests
pytest -q services/ingestion/tests

# 4. Format code
make fmt
```

### Step 4: Self-Review
Use this checklist:
- [ ] Tests pass: `pytest -q services/*/tests`
- [ ] Code formatted: `make fmt`
- [ ] No secrets in code
- [ ] Structured logging used
- [ ] Error handling comprehensive
- [ ] Documentation updated
- [ ] Security implications considered

### Step 5: Document Changes
Update relevant documentation:
- Service README for new endpoints
- `.env.example` for new environment variables
- `CHANGELOG.md` for user-facing changes
- Inline docstrings for complex logic

## 🔍 Code Quality Standards

### Readability
- Use descriptive variable names
- Keep functions under 50 lines
- Add docstrings for public functions
- Comment complex business logic only (code should be self-documenting)

### Pythonic Code
```python
# ✅ Good: Clear and idiomatic
def get_active_obligations(tenant_id: str) -> List[Obligation]:
    """Retrieve active obligations for a tenant."""
    return [
        obl for obl in obligations 
        if obl.tenant_id == tenant_id and obl.status == "active"
    ]

# ❌ Avoid: Verbose and unclear
def get_obligations_function(tenant_id_parameter):
    result_list = []
    for obligation_item in obligations:
        if obligation_item.tenant_id == tenant_id_parameter:
            if obligation_item.status == "active":
                result_list.append(obligation_item)
    return result_list
```

### Type Hints
Always use type hints:
```python
from typing import List, Optional, Dict, Any

def extract_text(pdf_bytes: bytes, page_limit: Optional[int] = None) -> str:
    """Extract text from PDF bytes."""
    pass
```

## 🚨 Common Pitfalls to Avoid

### ❌ Don't:
- Remove or modify working tests to make your code pass
- Commit commented-out code
- Use `print()` statements (use `logger` instead)
- Hard-code configuration (use environment variables)
- Ignore type hints or validation errors
- Make changes to `/shared/` without considering impact on all services
- Add dependencies without checking for alternatives

### ✅ Do:
- Use existing utilities and shared modules
- Follow the established project structure
- Keep commits focused and atomic
- Write clear commit messages
- Update tests when changing behavior
- Consider backward compatibility
- Run the full test suite before pushing

## 📊 Testing Guidelines

### Test Structure
```python
import pytest
from fastapi.testclient import TestClient

class TestIngestionEndpoint:
    """Tests for document ingestion API."""
    
    def test_ingest_url_success(self, client: TestClient, mock_s3):
        """Should ingest valid URL and return success."""
        response = client.post(
            "/ingest/url",
            json={"url": "https://example.gov/doc.pdf"},
            headers={"X-RegEngine-API-Key": "test-key"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_ingest_url_invalid_domain(self, client: TestClient):
        """Should reject URLs from non-whitelisted domains."""
        response = client.post(
            "/ingest/url",
            json={"url": "https://malicious.com/doc.pdf"},
            headers={"X-RegEngine-API-Key": "test-key"}
        )
        assert response.status_code == 400
```

### Test Coverage
- Happy path (successful execution)
- Edge cases (empty inputs, max limits)
- Error conditions (invalid data, network failures)
- Security scenarios (authentication, authorization, injection attacks)

## 🔐 Security Checklist

For every code change, verify:
- [ ] No hardcoded secrets or credentials
- [ ] User input is validated (use Pydantic models)
- [ ] SQL/Cypher queries are parameterized
- [ ] File uploads are scanned/validated
- [ ] API endpoints require authentication
- [ ] Rate limiting is applied where needed
- [ ] Errors don't leak sensitive information
- [ ] PII is encrypted if stored

## 🎓 Learning Resources

### Internal Documentation
- `shared/` - Security modules and utilities
- `services/*/README.md` - Service-specific documentation
- `.github/copilot-instructions.md` - Repository conventions
- `DEPLOYMENT.md` - Infrastructure and deployment

### External Resources
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Structlog Documentation](https://www.structlog.org/)

## 🤝 Collaboration with Humans

### Progress Updates
Provide regular updates:
- What you've completed
- What you're currently working on
- Any blockers or questions
- Estimated time to completion

### Handling Feedback
When you receive review feedback:
- Acknowledge the feedback
- Ask clarifying questions if needed
- Implement requested changes
- Explain your reasoning if you disagree (but defer to human judgment)

### Escalation
Escalate to humans when:
- Task is blocked by external factors
- You've attempted 3+ approaches without success
- Requirements fundamentally conflict
- Decision requires business/product context
- Security implications are serious

## 📝 Documentation Standards

### README Updates
When adding a new feature, update the service README:
```markdown
## New Feature: FSMA 204 Export

Generates FDA-compliant CSV exports for food traceability.

### Endpoint
`GET /v1/fsma/export/trace/{tlc}`

### Example
```bash
curl -X GET "http://localhost:8300/v1/fsma/export/trace/00123456789012345678" \
  -H "X-RegEngine-API-Key: your-key-here"
```

### Response
Returns a downloadable CSV file with forward/backward trace data.
```

### Inline Documentation
Use docstrings for complex functions:
```python
def calculate_compliance_score(
    obligations: List[Obligation],
    tenant_controls: Dict[str, Control]
) -> float:
    """Calculate compliance score based on obligation coverage.
    
    Implements the weighted scoring algorithm where:
    - MUST obligations: 1.0 weight
    - SHOULD obligations: 0.5 weight  
    - MAY obligations: 0.1 weight
    
    Args:
        obligations: List of regulatory obligations
        tenant_controls: Mapping of obligation IDs to implemented controls
        
    Returns:
        Score between 0.0 (no compliance) and 1.0 (full compliance)
        
    Example:
        >>> score = calculate_compliance_score(obligations, controls)
        >>> print(f"Compliance: {score:.1%}")
        Compliance: 87.5%
    """
```

## 🎯 Success Criteria

A successful agent contribution:
1. ✅ Solves the stated problem completely
2. ✅ Includes comprehensive tests
3. ✅ Follows all established patterns
4. ✅ Is well-documented
5. ✅ Passes all CI checks
6. ✅ Has no security vulnerabilities
7. ✅ Maintains backward compatibility
8. ✅ Is reviewed and approved by humans

Remember: **Your goal is to augment human developers, not replace them.** When in doubt, ask questions and seek guidance. We value thorough, secure, well-tested code over quick implementations.
