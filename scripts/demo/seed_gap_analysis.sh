#!/bin/bash
# Seed Neo4j with demo data for Gap Analysis
# This creates sample regulations for US and EU jurisdictions

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "🌱 Seeding Neo4j with Gap Analysis demo data..."

# Load password from .env
source .env 2>/dev/null || true
NEO4J_PASSWORD=${NEO4J_PASSWORD:-password}

# Wait for Neo4j
until curl -sf http://localhost:7474 > /dev/null 2>&1; do
    echo "   Waiting for Neo4j..."
    sleep 3
done

echo "   Neo4j is ready. Creating demo data..."

# Create demo data via cypher-shell
docker-compose exec -T neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" <<'CYPHER'

// Clean up existing demo data (optional - comment out to preserve)
// MATCH (n) DETACH DELETE n;

// Create Jurisdictions
MERGE (us:Jurisdiction {name: "US"})
SET us.full_name = "United States", us.region = "North America";

MERGE (eu:Jurisdiction {name: "EU"})
SET eu.full_name = "European Union", eu.region = "Europe";

// Create Demo Document
MERGE (doc_dora:Document {id: "dora-2022-2554"})
SET doc_dora.title = "Digital Operational Resilience Act (DORA)",
    doc_dora.source_url = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554",
    doc_dora.jurisdiction = "EU",
    doc_dora.created_at = datetime();

MERGE (doc_sec:Document {id: "sec-reg-sp"})
SET doc_sec.title = "SEC Regulation S-P",
    doc_sec.source_url = "https://www.sec.gov/rules/final/34-42974.htm",
    doc_sec.jurisdiction = "US",
    doc_sec.created_at = datetime();

MERGE (doc_gdpr:Document {id: "gdpr-2016-679"})
SET doc_gdpr.title = "General Data Protection Regulation (GDPR)",
    doc_gdpr.source_url = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679",
    doc_gdpr.jurisdiction = "EU",
    doc_gdpr.created_at = datetime();

MERGE (doc_ccpa:Document {id: "ccpa-2018"})
SET doc_ccpa.title = "California Consumer Privacy Act",
    doc_ccpa.source_url = "https://oag.ca.gov/privacy/ccpa",
    doc_ccpa.jurisdiction = "US",
    doc_ccpa.created_at = datetime();

// Create Concepts (regulatory topics)
MERGE (c_ict_risk:Concept {name: "ICT Risk Management"});
MERGE (c_incident:Concept {name: "Incident Reporting"});
MERGE (c_third_party:Concept {name: "Third-Party Risk"});
MERGE (c_data_breach:Concept {name: "Data Breach Notification"});
MERGE (c_data_retention:Concept {name: "Data Retention"});
MERGE (c_right_delete:Concept {name: "Right to Deletion"});
MERGE (c_penetration:Concept {name: "Penetration Testing"});
MERGE (c_audit_trail:Concept {name: "Audit Trail Requirements"});

// EU-only provisions (gaps when comparing US vs EU)
MERGE (p_dora_ict:Provision {id: "dora-art-5"})
SET p_dora_ict.text = "Financial entities shall have in place an internal governance and control framework that ensures an effective and prudent management of all ICT risks.",
    p_dora_ict.article = "Article 5",
    p_dora_ict.created_at = datetime();

MERGE (p_dora_ict)-[:ABOUT]->(c_ict_risk);
MERGE (p_dora_ict)-[:APPLIES_TO]->(eu);
MERGE (p_dora_ict)-[:IN_DOCUMENT]->(doc_dora);
MERGE (prov_dora_ict:Provenance {doc_id: "dora-2022-2554", start: 1200, end: 1450})
MERGE (p_dora_ict)-[:PROVENANCE]->(prov_dora_ict);

MERGE (p_dora_incident:Provision {id: "dora-art-17"})
SET p_dora_incident.text = "Financial entities shall report major ICT-related incidents to the competent authority within 4 hours of classification.",
    p_dora_incident.article = "Article 17",
    p_dora_incident.created_at = datetime();

MERGE (p_dora_incident)-[:ABOUT]->(c_incident);
MERGE (p_dora_incident)-[:APPLIES_TO]->(eu);
MERGE (p_dora_incident)-[:IN_DOCUMENT]->(doc_dora);
MERGE (prov_dora_incident:Provenance {doc_id: "dora-2022-2554", start: 4500, end: 4800})
MERGE (p_dora_incident)-[:PROVENANCE]->(prov_dora_incident);

MERGE (p_dora_pentest:Provision {id: "dora-art-26"})
SET p_dora_pentest.text = "Financial entities shall carry out advanced testing based on TLPT (Threat-Led Penetration Testing) at least every 3 years.",
    p_dora_pentest.article = "Article 26",
    p_dora_pentest.created_at = datetime();

MERGE (p_dora_pentest)-[:ABOUT]->(c_penetration);
MERGE (p_dora_pentest)-[:APPLIES_TO]->(eu);
MERGE (p_dora_pentest)-[:IN_DOCUMENT]->(doc_dora);
MERGE (prov_dora_pentest:Provenance {doc_id: "dora-2022-2554", start: 7200, end: 7500})
MERGE (p_dora_pentest)-[:PROVENANCE]->(prov_dora_pentest);

MERGE (p_gdpr_delete:Provision {id: "gdpr-art-17"})
SET p_gdpr_delete.text = "The data subject shall have the right to obtain from the controller the erasure of personal data concerning him or her without undue delay.",
    p_gdpr_delete.article = "Article 17",
    p_gdpr_delete.created_at = datetime();

MERGE (p_gdpr_delete)-[:ABOUT]->(c_right_delete);
MERGE (p_gdpr_delete)-[:APPLIES_TO]->(eu);
MERGE (p_gdpr_delete)-[:IN_DOCUMENT]->(doc_gdpr);
MERGE (prov_gdpr_delete:Provenance {doc_id: "gdpr-2016-679", start: 3200, end: 3500})
MERGE (p_gdpr_delete)-[:PROVENANCE]->(prov_gdpr_delete);

MERGE (p_gdpr_breach:Provision {id: "gdpr-art-33"})
SET p_gdpr_breach.text = "In the case of a personal data breach, the controller shall notify the supervisory authority within 72 hours.",
    p_gdpr_breach.article = "Article 33",
    p_gdpr_breach.created_at = datetime();

MERGE (p_gdpr_breach)-[:ABOUT]->(c_data_breach);
MERGE (p_gdpr_breach)-[:APPLIES_TO]->(eu);
MERGE (p_gdpr_breach)-[:IN_DOCUMENT]->(doc_gdpr);
MERGE (prov_gdpr_breach:Provenance {doc_id: "gdpr-2016-679", start: 5800, end: 6100})
MERGE (p_gdpr_breach)-[:PROVENANCE]->(prov_gdpr_breach);

// US-only provisions (gaps when comparing EU vs US)
MERGE (p_sec_safeguards:Provision {id: "sec-sp-30"})
SET p_sec_safeguards.text = "Every broker-dealer and investment adviser must adopt written policies and procedures addressing administrative, technical, and physical safeguards.",
    p_sec_safeguards.article = "Rule 30",
    p_sec_safeguards.created_at = datetime();

MERGE (p_sec_safeguards)-[:ABOUT]->(c_third_party);
MERGE (p_sec_safeguards)-[:APPLIES_TO]->(us);
MERGE (p_sec_safeguards)-[:IN_DOCUMENT]->(doc_sec);
MERGE (prov_sec_safeguards:Provenance {doc_id: "sec-reg-sp", start: 2100, end: 2400})
MERGE (p_sec_safeguards)-[:PROVENANCE]->(prov_sec_safeguards);

MERGE (p_ccpa_retention:Provision {id: "ccpa-1798-105"})
SET p_ccpa_retention.text = "A business shall not retain personal information for longer than is reasonably necessary for the disclosed purpose.",
    p_ccpa_retention.article = "Section 1798.105",
    p_ccpa_retention.created_at = datetime();

MERGE (p_ccpa_retention)-[:ABOUT]->(c_data_retention);
MERGE (p_ccpa_retention)-[:APPLIES_TO]->(us);
MERGE (p_ccpa_retention)-[:IN_DOCUMENT]->(doc_ccpa);
MERGE (prov_ccpa_retention:Provenance {doc_id: "ccpa-2018", start: 1500, end: 1800})
MERGE (p_ccpa_retention)-[:PROVENANCE]->(prov_ccpa_retention);

MERGE (p_sec_audit:Provision {id: "sec-17a-4"})
SET p_sec_audit.text = "Broker-dealers must preserve records for a period of not less than six years, with the first two years in an easily accessible place.",
    p_sec_audit.article = "Rule 17a-4",
    p_sec_audit.created_at = datetime();

MERGE (p_sec_audit)-[:ABOUT]->(c_audit_trail);
MERGE (p_sec_audit)-[:APPLIES_TO]->(us);
MERGE (p_sec_audit)-[:IN_DOCUMENT]->(doc_sec);
MERGE (prov_sec_audit:Provenance {doc_id: "sec-reg-sp", start: 800, end: 1100})
MERGE (p_sec_audit)-[:PROVENANCE]->(prov_sec_audit);

// Return summary
MATCH (j:Jurisdiction) RETURN "Jurisdictions: " + count(j) AS summary
UNION ALL
MATCH (c:Concept) RETURN "Concepts: " + count(c) AS summary
UNION ALL
MATCH (p:Provision) RETURN "Provisions: " + count(p) AS summary
UNION ALL
MATCH (d:Document) RETURN "Documents: " + count(d) AS summary;

CYPHER

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Demo data seeded successfully!"
    echo ""
    echo "   Try the Gap Analysis:"
    echo "   • US vs EU: Shows EU regulations not in US (DORA, GDPR)"
    echo "   • EU vs US: Shows US regulations not in EU (SEC, CCPA)"
    echo ""
else
    echo "❌ Failed to seed demo data"
    exit 1
fi
