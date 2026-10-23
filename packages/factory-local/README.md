# factory-local

This package processes supplied legislative text into a DeonticIR, verifies the
rule with Z3, compiles Rego, and can write signed evaluation receipts. It is
separate from the production RegEngine application.

No bills, rules, lobbying relationships, statutory text, or expected evaluation
cases are bundled. With no input, the CLIs print `No data yet` and do not call
external services.

## Commands

Run the live LegiScan path only when a specific bill or state scan is selected:

```bash
cd packages/factory-local
./bootstrap.sh --bill BILL_NUMBER --state STATE_CODE --tenant TENANT_ID
.venv/bin/python app/local_factory.py --bill-id LEGISCAN_BILL_ID --tenant TENANT_ID
.venv/bin/python app/local_factory.py --scan-state --state STATE_CODE --tenant TENANT_ID
```

`LEGISCAN_API_KEY` and a tenant ID are required for these paths. The live bill path retrieves the
latest available text, requests structured extraction from the configured LLM,
checks the rule with Z3, embeds and stores the bill version, and checks for
copycat candidates. Rules below the opportunity threshold or failing Z3 are
not deployed. Successful rules compile to `cartridges/` and are evaluated with
boundary cases derived from that rule. There is no default bill.

`./bootstrap.sh` without arguments prints `No data yet` before creating a
virtual environment, reading configuration, or starting containers. With a
bill or state selection, it installs the locked dependencies, starts the local
Compose services, and runs the live path.

For text already obtained from a source, supply the file and its metadata:

```bash
.venv/bin/python pipeline.py run \
  --text PATH_TO_TEXT --bill-id BILL_ID --version-uid VERSION_UID \
  --title TITLE --jurisdiction JURISDICTION --source-uri SOURCE_URI
.venv/bin/python pipeline.py verify-chain
.venv/bin/streamlit run approval_ui.py --server.port 8501
```

`pipeline.py run` requires `OLLAMA_MODEL` and a valid structured model response.
It stores no rule when text, metadata, a model, or a valid response is missing.
The approval screen is read only until verified evaluation cases are supplied.
`pipeline.approve(rule_uid, cases=..., tenant_id=...)` accepts explicit cases through the
Python API; the CLI without cases returns `No data yet` and makes no changes.
`verify-chain` checks the receipts already stored for a tenant.

The graph loader also requires explicit input:

```bash
.venv/bin/python app/seed_neo4j.py --graph PATH_TO_GRAPH_JSON
```

The graph JSON uses the node collections and relationship types declared in
`app/seed_neo4j.py`. Without a graph path or with an empty graph, it prints
`No data yet` without connecting to Neo4j. The buyer intent query only returns
rows present in the database. Its results are leads to inspect, not established
lobbying facts.

## Components

| File | Role |
| --- | --- |
| `schemas.py` | Validates the DeonticIR and safe fact/control identifiers. |
| `extract.py` | Extracts structured IR from supplied text through Ollama. |
| `compiler.py` | Compiles verified IR to Rego v1. |
| `verify.py` | Checks status completeness, overlap, and cross-rule collisions with Z3. |
| `pipeline.py` | Stores supplied text and IR, deploys approved rules, and checks receipt chains. |
| `ledger.py` | Canonical hashing, Ed25519 signing, and tenant receipt-chain verification. |
| `app/local_factory.py` | Live LegiScan bill and state-scan processing. |
| `app/seed_neo4j.py` | Explicit graph import and buyer intent query. |
| `approval_ui.py` | Human review of rules already stored. |

## Tests

```bash
.venv/bin/python -m pytest -m "not integration"
```

The tests cover only empty and missing input paths. They no longer assert
example bill extraction, sample graph relationships, OPA outcomes, copycat
matches, or receipt chains. These paths need verified, source-backed inputs
before meaningful end-to-end testing resumes.
