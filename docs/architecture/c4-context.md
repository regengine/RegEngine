# C4 Model: System Context (Level 1)

## Diagram

```mermaid
graph TB
    subgraph users["Users"]
        CA[👤 Compliance Analyst<br/>Reviews obligations,<br/>validates extractions]
        SA[👤 System Admin<br/>Manages tenants,<br/>API keys]
        DEV[👤 Developer<br/>Integrates via API]
    end
    
    subgraph regengine["RegEngine Platform"]
        RE[📦 RegEngine<br/>Regulatory Intelligence<br/>Platform]
    end
    
    subgraph external["External Systems"]
        EURLEX[🌐 EUR-Lex<br/>EU Regulations]
        SEC[🌐 SEC EDGAR<br/>US Securities]
        NYDFS[🌐 NY DFS<br/>NY Financial]
        CPPA[🌐 CPPA<br/>CA Privacy]
        OLLAMA[🤖 Ollama<br/>LLM Service]
    end
    
    CA -->|Reviews extractions,<br/>validates compliance| RE
    SA -->|Manages tenants,<br/>rotates keys| RE
    DEV -->|REST API calls| RE
    
    RE -->|Fetches regulations| EURLEX
    RE -->|Fetches regulations| SEC
    RE -->|Fetches regulations| NYDFS
    RE -->|Fetches regulations| CPPA
    RE -->|NLP extraction| OLLAMA
```

## Context Description

### Users

| Actor | Role | Interactions |
|-------|------|--------------|
| **Compliance Analyst** | Reviews extracted obligations, validates against checklists | UI: Review queue, Compliance page, Opportunities |
| **System Admin** | Manages multi-tenant configuration | UI: Admin page, API key management |
| **Developer** | Integrates RegEngine into workflows | REST API: Ingestion, Query, Webhooks |

### External Systems

| System | Integration | Data Flow |
|--------|-------------|-----------|
| **EUR-Lex** | HTTP scraping | Inbound: EU regulations (DORA, MiCA, etc.) |
| **SEC EDGAR** | HTTP scraping | Inbound: US securities regulations |
| **NY DFS** | HTTP scraping | Inbound: NY financial regulations |
| **CPPA** | HTTP scraping | Inbound: California privacy regulations |
| **Ollama** | REST API | Bidirectional: NLP extraction requests/responses |

## Key Relationships

1. **RegEngine → External Regulatory Sources**: Pull-based ingestion triggered by user or scheduler
2. **RegEngine → Ollama**: Synchronous LLM calls for entity extraction
3. **Users → RegEngine**: HTTPS with API key authentication
4. **RegEngine → Users**: Real-time UI updates, webhook notifications (future)

## Quality Attributes at this Level

- **Availability**: Platform must be accessible 99.9% uptime
- **Security**: All external communications over TLS, API key auth
- **Auditability**: All user actions logged with correlation IDs
