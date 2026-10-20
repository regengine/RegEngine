# factory-local

A self-contained local pipeline that turns statutory text into a verified,
human-approved OPA policy and writes signed, hash-chained receipts for every
evaluation.

```text
statute text -> DeonticIR (Ollama or fixture) -> Rego + Z3 proof -> human approval
             -> OPA cartridge -> evaluation -> Ed25519 signed receipt chain (Postgres)
```

This package is a standalone demo. It does not import from or deploy with the
RegEngine application.

## Pieces

| File | Role |
| --- | --- |
| `schemas.py` | `DeonticPredicate` and `DeonticIR` (pydantic). Fact and control names are validated as safe identifiers. |
| `compiler.py` | `compile_ir_to_rego(ir, pkg)` emits Rego v1 with strict status precedence. |
| `verify.py` | Z3 formulas built from the IR. Proves the statuses are disjoint and complete; finds cross-rule exempt/obligated collisions with a concrete model. |
| `ledger.py` | RFC 8785 canonical hashing, Ed25519 signatures, per-tenant advisory lock, `verify_chain`. |
| `extract.py` | Ollama structured extraction with fixture fallback. Never pulls models. |
| `graph.py` | Seeds Neo4j with the bill, sections, versions, and one fictional `ExampleOrg`. |
| `pipeline.py` | CLI: `run`, `approve --rule`, `verify-chain`. |
| `approval_ui.py` | Streamlit review screen with an Approve & Deploy button. |
| `db_init/01_init.sql` | Tables, plus an append-only trigger on the ledger. |

## Status logic

Highest precedence first. Missing control keys behave as false.

1. `COMPLIANT`: applicable and the required action is done
2. `COMPLIANT_VIA_SAFE_HARBOR`: applicable, action not done, safe harbor control true
3. `NON_COMPLIANT_BREACH`: applicable, action not done, no safe harbor
4. `EXEMPT_OR_NOT_APPLICABLE`: default, including when a fact is missing

On breach, `violation_exposure_usd = affected_consumer_count * max_penalty_usd`, else 0.
For `PROHIBITION` rules, "action done" means the control is not true.

## Run it

```bash
cd packages/factory-local
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
docker compose up -d --wait
.venv/bin/python pipeline.py run
.venv/bin/python pipeline.py approve --rule US_CO_SB205_V2
.venv/bin/python pipeline.py verify-chain
.venv/bin/streamlit run approval_ui.py --server.port 8501
```

If a local Postgres already uses 5432, set `FACTORY_PG_PORT=55432` (and
`FACTORY_OPA_PORT`, `FACTORY_NEO4J_BOLT_PORT` as needed) for both
`docker compose` and the Python commands.

Set `OLLAMA_MODEL` to a model you already have locally to use live extraction.
Without it, or if Ollama fails or returns invalid JSON, the pipeline uses
`fixtures/co_sb205_ir.json` and records the reason as `extraction_source`.

`fixtures/co_sb205_text.txt` is a paraphrase for the demo, not the statute.

## Keys

`ledger.py` creates `.keys/ed25519.pem` (mode 600) on first approve. `.keys/`
is gitignored. Losing the key means old receipts still verify with the public
key you kept, but new receipts start signing with a new key.

## Tests

```bash
.venv/bin/python -m pytest -m "not integration"   # offline, no services
.venv/bin/python -m pytest -m integration         # needs OPA + Postgres up
```

## Known limits

- Bind mounts only work for paths the Docker VM shares. Colima shares only
  the directories listed under `mounts:` in `~/.colima/default/colima.yaml`,
  and a path that is not listed shows up empty inside the container. The
  pipeline handles this: `run` applies `db_init/01_init.sql` itself (it is
  idempotent), and `approve` waits 10 seconds for OPA `--watch` to load the
  cartridge. If OPA has not loaded it by then, `approve` pushes the same text
  through `PUT /v1/policies`. Either way it confirms that the loaded text
  matches the verified Rego exactly. `opa_loaded_via` in the output reports
  `watch` or `api`.
- Z3 checks the status logic built from the IR, not the generated Rego text.
  The two are kept in step by hand and by tests.
- `approve` marks the rule `human_verified` before deployment finishes. If OPA
  or an assertion fails afterwards, the flag stays true and no receipt is
  written.
- Compose default credentials are local dev values. Do not reuse them.
