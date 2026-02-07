# C4 Model: Component Diagram (Level 3)

## Admin Service Components

```mermaid
graph TB
    subgraph admin["Admin API :8400"]
        AR[Routes<br/>routes.py]
        AM[Models<br/>models.py]
        ADB[Database<br/>database.py]
        AME[Metrics<br/>metrics.py]
        ARC[Review Consumer<br/>review_consumer.py]
    end
    
    AR --> AM
    AR --> ADB
    AR --> AME
    ARC --> ADB
    ARC --> AME
    
    subgraph external
        PG[(PostgreSQL)]
        KAFKA[Kafka]
    end
    
    ADB --> PG
    ARC --> KAFKA
```

| Component | File | Responsibility |
|-----------|------|----------------|
| **Routes** | `routes.py` | API endpoints for tenants, keys, review |
| **Models** | `models.py` | Pydantic models, TenantContext |
| **Database** | `database.py` | SQLAlchemy session management |
| **Metrics** | `metrics.py` | HallucinationTracker, Prometheus |
| **Review Consumer** | `review_consumer.py` | Kafka consumer for low-confidence items |

---

## Ingestion Service Components

```mermaid
graph TB
    subgraph ingestion["Ingestion :8000"]
        IR[Routes<br/>routes.py]
        IN[Normalizer<br/>normalizer.py]
        IS3[S3 Utils<br/>s3_utils.py]
        ISC[Scrapers<br/>scrapers/]
    end
    
    IR --> IN
    IR --> IS3
    IR --> ISC
    
    subgraph external
        S3[(S3/MinIO)]
        KAFKA[Kafka]
        WEB[External URLs]
    end
    
    IS3 --> S3
    IR --> KAFKA
    ISC --> WEB
```

| Component | File | Responsibility |
|-----------|------|----------------|
| **Routes** | `routes.py` | `/ingest/url`, `/scrape/*` endpoints |
| **Normalizer** | `normalizer.py` | PDF/HTML extraction, hashing |
| **S3 Utils** | `s3_utils.py` | Raw/normalized document storage |
| **Scrapers** | `scrapers/` | NYDFS, CPPA, generic state adapters |

---

## NLP Service Components

```mermaid
graph TB
    subgraph nlp["NLP :8100"]
        NC[Consumer<br/>consumer.py]
        NE[Extractors<br/>extractors/]
        NTL[Text Loader<br/>text_loader.py]
    end
    
    NC --> NE
    NC --> NTL
    
    subgraph external
        KAFKA[Kafka]
        S3[(S3)]
        OLLAMA[Ollama LLM]
    end
    
    NC --> KAFKA
    NTL --> S3
    NE --> OLLAMA
```

| Component | File | Responsibility |
|-----------|------|----------------|
| **Consumer** | `consumer.py` | Kafka consumer, confidence routing |
| **Extractors** | `extractors/` | NYDFS, SEC, generic extractors |
| **Text Loader** | `text_loader.py` | S3 fetch, PDF/HTML parsing |

---

## Graph Service Components

```mermaid
graph TB
    subgraph graph["Graph :8200"]
        GR[Routes<br/>routes.py]
        GC[Consumer<br/>consumer.py]
        GNU[Neo4j Utils<br/>neo4j_utils.py]
        GOW[Overlay Writer<br/>overlay_writer.py]
        GEP[Event Publisher<br/>graph_event_publisher.py]
    end
    
    GR --> GNU
    GC --> GNU
    GC --> GOW
    GOW --> GEP
    
    subgraph external
        NEO[(Neo4j)]
        KAFKA[Kafka]
    end
    
    GNU --> NEO
    GC --> KAFKA
    GEP --> KAFKA
```

| Component | File | Responsibility |
|-----------|------|----------------|
| **Routes** | `routes.py` | `/v1/provisions/*` queries |
| **Consumer** | `consumer.py` | `graph.update` Kafka consumer |
| **Neo4j Utils** | `neo4j_utils.py` | Driver, upsert operations |
| **Overlay Writer** | `overlay_writer.py` | Tenant controls, mappings |
| **Event Publisher** | `graph_event_publisher.py` | Audit events to Kafka |

---

## Compliance Service Components

```mermaid
graph TB
    subgraph compliance["Compliance :8500"]
        CM[Main<br/>main.py]
        CCE[Checklist Engine<br/>checklist_engine.py]
        CFE[FSMA Engine<br/>fsma_engine.py]
    end
    
    CM --> CCE
    CM --> CFE
    
    subgraph external
        PLUGINS[Industry Plugins]
        NEO[(Neo4j)]
    end
    
    CCE --> PLUGINS
    CFE --> NEO
```

| Component | File | Responsibility |
|-----------|------|----------------|
| **Main** | `main.py` | FastAPI app, endpoints |
| **Checklist Engine** | `checklist_engine.py` | Plugin loading, validation |
| **FSMA Engine** | `fsma_engine.py` | Food safety assessment |

---

## Opportunity Service Components

```mermaid
graph TB
    subgraph opportunity["Opportunity :8300"]
        OR[Routes<br/>routes.py]
        ONU[Neo4j Utils<br/>neo4j_utils.py]
    end
    
    OR --> ONU
    
    subgraph external
        NEO[(Neo4j)]
    end
    
    ONU --> NEO
```

| Component | File | Responsibility |
|-----------|------|----------------|
| **Routes** | `routes.py` | `/opportunities/arbitrage`, `/opportunities/gaps` |
| **Neo4j Utils** | `neo4j_utils.py` | Cypher queries for comparison |
