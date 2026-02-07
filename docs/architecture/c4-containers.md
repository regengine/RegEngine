# C4 Model: Container Diagram (Level 2)

## Diagram

```mermaid
graph TB
    subgraph users["Users"]
        USER[👤 User]
    end
    
    subgraph frontend["Frontend"]
        FE[📱 Next.js App<br/>:3000<br/>React, TypeScript]
    end
    
    subgraph gateway["Gateway"]
        GW[🚪 Nginx<br/>:80<br/>Reverse Proxy]
    end
    
    subgraph services["Backend Services"]
        ADMIN[🔐 Admin API<br/>:8400<br/>FastAPI, Python]
        ING[📥 Ingestion<br/>:8000<br/>FastAPI, Python]
        NLP[🧠 NLP Service<br/>:8100<br/>FastAPI, Python]
        GRAPH[🔗 Graph Service<br/>:8200<br/>FastAPI, Python]
        COMP[✅ Compliance API<br/>:8500<br/>FastAPI, Python]
        OPP[🔍 Opportunity API<br/>:8300<br/>FastAPI, Python]
    end
    
    subgraph messaging["Messaging"]
        KAFKA[📨 Redpanda<br/>:9092<br/>Kafka-compatible]
    end
    
    subgraph data["Data Stores"]
        PG[(🐘 PostgreSQL<br/>:5432<br/>Admin DB)]
        NEO[(🔵 Neo4j<br/>:7687<br/>Knowledge Graph)]
        S3[(📦 MinIO/S3<br/>:4566<br/>Document Storage)]
        REDIS[(⚡ Redis<br/>:6379<br/>Cache/Rate Limit)]
    end
    
    USER --> FE
    FE --> GW
    GW --> ADMIN & ING & COMP & OPP
    
    ING --> S3
    ING --> KAFKA
    KAFKA --> NLP
    NLP --> KAFKA
    KAFKA --> GRAPH
    KAFKA --> ADMIN
    
    GRAPH --> NEO
    ADMIN --> PG
    OPP --> NEO
    COMP --> NEO
    
    ADMIN --> REDIS
    ING --> REDIS
```

## Container Descriptions

### Frontend Layer

| Container | Technology | Responsibility |
|-----------|------------|----------------|
| **Next.js App** | React 18, TypeScript, Tailwind | User interface, SSR, API routes |

### API Gateway

| Container | Technology | Responsibility |
|-----------|------------|----------------|
| **Nginx** | Alpine | Request routing, TLS termination, load balancing |

### Backend Services

| Container | Port | Technology | Responsibility |
|-----------|------|------------|----------------|
| **Admin API** | 8400 | FastAPI | Tenant management, API keys, review queue |
| **Ingestion** | 8000 | FastAPI | URL fetching, normalization, S3 storage |
| **NLP Service** | 8100 | FastAPI | Entity extraction, confidence scoring |
| **Graph Service** | 8200 | FastAPI | Neo4j ingestion, provision queries |
| **Compliance API** | 8500 | FastAPI | Checklist validation, FSMA assessment |
| **Opportunity API** | 8300 | FastAPI | Arbitrage detection, gap analysis |

### Messaging

| Container | Technology | Topics |
|-----------|------------|--------|
| **Redpanda** | Kafka-compatible | `ingest.normalized`, `graph.update`, `nlp.needs_review`, `graph.audit` |

### Data Stores

| Container | Technology | Data |
|-----------|------------|------|
| **PostgreSQL** | v15 | Tenants, API keys, review queue |
| **Neo4j** | v5.24 | Provisions, jurisdictions, thresholds |
| **MinIO/S3** | S3-compatible | Raw documents, normalized JSON |
| **Redis** | v7 | Rate limiting, session cache |

## Communication Patterns

1. **Sync (HTTP)**: Frontend → Gateway → Services
2. **Async (Kafka)**: Ingestion → NLP → Graph/Admin
3. **Query (Bolt/SQL)**: Services → Neo4j/PostgreSQL
