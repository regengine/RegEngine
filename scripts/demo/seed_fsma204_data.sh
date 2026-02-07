#!/bin/bash
# Seed Neo4j with FSMA 204 and food industry regulatory demo data

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$PROJECT_ROOT"

echo "🌱 Seeding Neo4j with FSMA 204 regulatory data..."

source .env 2>/dev/null || true
NEO4J_PASSWORD=${NEO4J_PASSWORD:-password}

until curl -sf http://localhost:7474 > /dev/null 2>&1; do
    echo "   Waiting for Neo4j..."
    sleep 3
done

echo "   Neo4j is ready. Creating FSMA 204 demo data..."

# Create base entities
docker-compose exec -T neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" <<'CYPHER'
// Jurisdictions
MERGE (j:Jurisdiction {name: "FSMA-204"}) SET j.full_name = "FDA FSMA Section 204", j.region = "United States";
MERGE (j:Jurisdiction {name: "EU-HACCP"}) SET j.full_name = "EU HACCP", j.region = "European Union";
MERGE (j:Jurisdiction {name: "GFSI"}) SET j.full_name = "Global Food Safety Initiative", j.region = "International";

// Documents
MERGE (:Document {id: "fsma-204-rule", title: "FDA Food Traceability Final Rule", source_url: "https://www.fda.gov/food/fsma-rule-requirements"});
MERGE (:Document {id: "food-traceability-list", title: "FDA Food Traceability List", source_url: "https://www.fda.gov/food/food-traceability-list"});
MERGE (:Document {id: "eu-178-2002", title: "EU General Food Law 178/2002", source_url: "https://eur-lex.europa.eu"});
MERGE (:Document {id: "gfsi-benchmarking", title: "GFSI Benchmarking Requirements", source_url: "https://mygfsi.com/benchmarking"});

// Concepts
MERGE (:Concept {name: "Traceability Lot Code"});
MERGE (:Concept {name: "Critical Tracking Events"});
MERGE (:Concept {name: "Key Data Elements"});
MERGE (:Concept {name: "24-Hour Response Requirement"});
MERGE (:Concept {name: "Food Traceability List"});
MERGE (:Concept {name: "HACCP Plan"});
MERGE (:Concept {name: "Temperature Control"});
MERGE (:Concept {name: "Supplier Verification"});
MERGE (:Concept {name: "Recall Procedures"});

// Provisions
MERGE (:Provision {id: "fsma-204-tlc", text: "Each food on the FTL must be assigned a unique Traceability Lot Code (TLC).", article: "21 CFR 1.1310"});
MERGE (:Provision {id: "fsma-204-cte", text: "Firms must maintain records for all CTEs: growing, receiving, transforming, creating, shipping.", article: "21 CFR 1.1315"});
MERGE (:Provision {id: "fsma-204-kde", text: "For each CTE, KDEs must include: TLC, location, date, quantity, product description.", article: "21 CFR 1.1320"});
MERGE (:Provision {id: "fsma-204-24hr", text: "Within 24 hours of FDA request, provide records in electronic sortable format.", article: "21 CFR 1.1455"});
MERGE (:Provision {id: "fsma-204-ftl", text: "FTL includes: leafy greens, tomatoes, peppers, finfish, shellfish, eggs, nut butters.", article: "21 CFR 1.1300"});
MERGE (:Provision {id: "eu-haccp-plan", text: "Food operators must implement HACCP principles with hazard ID and critical control points.", article: "Reg 852/2004"});
MERGE (:Provision {id: "eu-temperature", text: "Temperature-controlled food must maintain cold chain throughout storage and transport.", article: "Reg 853/2004"});
MERGE (:Provision {id: "gfsi-supplier", text: "Sites must have documented supplier verification with risk assessment and monitoring.", article: "GFSI 2.5.3"});
MERGE (:Provision {id: "gfsi-recall", text: "Documented recall procedure required including annual mock recall exercises.", article: "GFSI 3.9"});

// Provenances
MERGE (:Provenance {doc_id: "fsma-204-rule", start: 100, end: 300});
MERGE (:Provenance {doc_id: "fsma-204-rule", start: 400, end: 600});
MERGE (:Provenance {doc_id: "fsma-204-rule", start: 700, end: 900});
MERGE (:Provenance {doc_id: "fsma-204-rule", start: 1000, end: 1200});
MERGE (:Provenance {doc_id: "food-traceability-list", start: 50, end: 250});
MERGE (:Provenance {doc_id: "eu-178-2002", start: 100, end: 300});
MERGE (:Provenance {doc_id: "eu-178-2002", start: 400, end: 600});
MERGE (:Provenance {doc_id: "gfsi-benchmarking", start: 100, end: 300});
MERGE (:Provenance {doc_id: "gfsi-benchmarking", start: 400, end: 600});
CYPHER

# Create relationships
docker-compose exec -T neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" <<'CYPHER'
// FSMA-204 provisions relationships
MATCH (p:Provision {id: "fsma-204-tlc"}), (c:Concept {name: "Traceability Lot Code"}), (j:Jurisdiction {name: "FSMA-204"}), (d:Document {id: "fsma-204-rule"}), (prov:Provenance {doc_id: "fsma-204-rule", start: 100})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

MATCH (p:Provision {id: "fsma-204-cte"}), (c:Concept {name: "Critical Tracking Events"}), (j:Jurisdiction {name: "FSMA-204"}), (d:Document {id: "fsma-204-rule"}), (prov:Provenance {doc_id: "fsma-204-rule", start: 400})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

MATCH (p:Provision {id: "fsma-204-kde"}), (c:Concept {name: "Key Data Elements"}), (j:Jurisdiction {name: "FSMA-204"}), (d:Document {id: "fsma-204-rule"}), (prov:Provenance {doc_id: "fsma-204-rule", start: 700})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

MATCH (p:Provision {id: "fsma-204-24hr"}), (c:Concept {name: "24-Hour Response Requirement"}), (j:Jurisdiction {name: "FSMA-204"}), (d:Document {id: "fsma-204-rule"}), (prov:Provenance {doc_id: "fsma-204-rule", start: 1000})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

MATCH (p:Provision {id: "fsma-204-ftl"}), (c:Concept {name: "Food Traceability List"}), (j:Jurisdiction {name: "FSMA-204"}), (d:Document {id: "food-traceability-list"}), (prov:Provenance {doc_id: "food-traceability-list", start: 50})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

// EU-HACCP provisions relationships
MATCH (p:Provision {id: "eu-haccp-plan"}), (c:Concept {name: "HACCP Plan"}), (j:Jurisdiction {name: "EU-HACCP"}), (d:Document {id: "eu-178-2002"}), (prov:Provenance {doc_id: "eu-178-2002", start: 100})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

MATCH (p:Provision {id: "eu-temperature"}), (c:Concept {name: "Temperature Control"}), (j:Jurisdiction {name: "EU-HACCP"}), (d:Document {id: "eu-178-2002"}), (prov:Provenance {doc_id: "eu-178-2002", start: 400})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

// GFSI provisions relationships
MATCH (p:Provision {id: "gfsi-supplier"}), (c:Concept {name: "Supplier Verification"}), (j:Jurisdiction {name: "GFSI"}), (d:Document {id: "gfsi-benchmarking"}), (prov:Provenance {doc_id: "gfsi-benchmarking", start: 100})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

MATCH (p:Provision {id: "gfsi-recall"}), (c:Concept {name: "Recall Procedures"}), (j:Jurisdiction {name: "GFSI"}), (d:Document {id: "gfsi-benchmarking"}), (prov:Provenance {doc_id: "gfsi-benchmarking", start: 400})
MERGE (p)-[:ABOUT]->(c) MERGE (p)-[:APPLIES_TO]->(j) MERGE (p)-[:IN_DOCUMENT]->(d) MERGE (p)-[:PROVENANCE]->(prov);

// Summary
MATCH (j:Jurisdiction) RETURN "Jurisdictions: " + count(j) AS summary
UNION ALL MATCH (p:Provision) RETURN "Provisions: " + count(p) AS summary;
CYPHER

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ FSMA 204 regulatory data seeded successfully!"
    echo ""
    echo "   Gap Analysis examples now available:"
    echo "   • FSMA-204 vs EU-HACCP"
    echo "   • US vs GFSI"
    echo ""
else
    echo "❌ Failed to seed FSMA 204 data"
    exit 1
fi
