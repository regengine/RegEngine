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
| `compiler.py` | `compile_ir_to_rego(ir, pkg)` emits Rego v1 with strict `compliance_status` precedence. |
| `verify.py` | Z3 formulas built from the IR. Proves the compliance statuses are disjoint and complete; finds cross-rule exempt/obligated collisions with a concrete model. |
| `ledger.py` | RFC 8785 canonical hashing, Ed25519 signatures, per-tenant advisory lock, `verify_chain`. |
| `extract.py` | Ollama structured extraction with fixture fallback. Never pulls models. |
| `graph.py` | Seeds Neo4j with the bill, sections, versions, and one fictional `ExampleOrg`. |
| `pipeline.py` | CLI: `run`, `approve --rule`, `verify-chain`. |
| `app/local_factory.py` | One-shot dry run with the fixture (no approval step, no Neo4j), a live LegiScan bill with `--bill` / `--bill-id`, or a ranked state scan with `--scan-state`. |
| `bootstrap.sh` | venv, `.env`, compose stack, then the dry run. |
| `approval_ui.py` | Streamlit review screen with an Approve & Deploy button. |
| `db_init/01_init.sql` | Tables, plus an append-only trigger on the ledger. |
| `db_init/02_live_bill.sql` | Adds `bill_versions.version_stage` and `extracted_rules.opportunity_score_vs` for live bills. |
| `app/seed_neo4j.py` | Seeds Neo4j with the SAMPLE lobbying graph in `fixtures/sample_lobbying_graph.json` and prints a buyer intent table. |

## compliance_status logic

The Rego `result` object reports it as `compliance_status`. Each body excludes
the ones above it, so no two can hold at once. Highest precedence first.
Missing control keys behave as false.

1. `COMPLIANT`: applicable and the required action is done
2. `COMPLIANT_VIA_SAFE_HARBOR`: applicable, action not done, safe harbor control true
3. `NON_COMPLIANT_BREACH`: applicable, action not done, no safe harbor
4. `EXEMPT_OR_NOT_APPLICABLE`: default, including when a fact is missing

On breach, `violation_exposure_usd = affected_consumer_count * max_penalty_usd`, else 0.
For `PROHIBITION` rules, "action done" means the control is not true.

## Run it

```bash
cd packages/factory-local
./bootstrap.sh
```

`bootstrap.sh` is safe to re-run. It creates `.venv` and installs
`requirements.lock` with `--require-hashes` (again only when the lock changes),
creates `.env` from `.env.example` with generated passwords if `.env` is missing
(it never prints them), runs `docker compose up -d --wait`, then runs
`app/local_factory.py`. That entrypoint takes the SB 24-205 fixture through Z3
verification, Rego compile, cartridge write, OPA evaluation, Ed25519 signed
receipts on the Postgres hash chain, and a full chain check. It skips the human
approval step and Neo4j.

The step by step flow with human approval:

```bash
set -a; . ./.env; set +a        # the Python commands read the same variables
.venv/bin/python pipeline.py run
.venv/bin/python pipeline.py approve --rule US_CO_SB205_V2
.venv/bin/python pipeline.py verify-chain
.venv/bin/streamlit run approval_ui.py --server.port 8501
docker compose down
```

If a local Postgres already uses 5432, export `FACTORY_PG_PORT=55432` (and
`FACTORY_OPA_PORT`, `FACTORY_NEO4J_BOLT_PORT`, `FACTORY_NEO4J_HTTP_PORT` as
needed) before `./bootstrap.sh`, `docker compose`, and the Python commands.

Set `OLLAMA_MODEL` to a model you already have locally to use live extraction.
Without it, or if Ollama fails or returns invalid JSON, the pipeline uses
`fixtures/co_sb205_ir.json` and records the reason as `extraction_source`.

`fixtures/co_sb205_text.txt` is a paraphrase for the demo, not the statute.

## Live bill from LegiScan

```bash
set -a; . ./.env; set +a                                    # .env holds LEGISCAN_API_KEY
.venv/bin/python app/local_factory.py --bill SB205 --state CO
.venv/bin/python app/local_factory.py --bill HR1 --state US  # Congress
.venv/bin/python app/local_factory.py --bill-id 1789123      # exact LegiScan bill_id, no search
./bootstrap.sh --bill SB205                                  # same, after setup
```

With no arguments the script runs the fixture dry run exactly as before. With
`--bill` or `--bill-id` it:

1. Finds the bill with LegiScan `getSearch` (exact bill number, all sessions, most
   recent last action wins; use `--bill-id` to pin one), then `getBill` and
   `getBillText` for the latest text by date. HTML is stripped with BeautifulSoup,
   PDF is read with pypdf. Other formats stop the run with an error.
2. Sends the first 45000 characters to an OpenAI compatible endpoint with
   structured output (`DeonticIR` plus `opportunity_score_vs`), temperature 0.
   `rule_id` is forced to the bill uid, for example `CO_SB205_2061` (state, bill
   number, LegiScan session id).
3. Runs the Z3 checks from `verify.py`, plus a check that a breach input exists.
   Z3 Optimize picks a synthetic payload sitting on each numeric threshold.
4. Gates the bill. It continues only when `opportunity_score_vs` is 70 or more
   and Z3 verifies it. Otherwise the run prints `SKIPPED <bill uid>: <reason>` to
   stderr and stores and deploys nothing. A low score exits 0; a Z3 failure exits 1.
5. Compiles `package cartridge.<slug>` to `cartridges/<slug>.rego`.
6. Stores the bill version (`<bill uid>@<doc_id>`, with `version_stage`) and the rule
   in Postgres with `human_verified = false`.
7. Calls `pipeline.deploy_and_record()`: OPA load, evaluation of the boundary
   breach and boundary safe harbor payloads at `/v1/data/cartridge/<slug>`, one
   signed receipt per case on the tenant's hash chain, and a full chain check.

The system prompt gives the model a rubric for `opportunity_score_vs` (0 to 100):
breadth of regulated entities (up to 30), enforcement severity (up to 25),
recurring work software can automate (up to 25), and certainty and timing (up to 20).

### Scan a state

```bash
.venv/bin/python app/local_factory.py --scan-state --state CA            # top 5
.venv/bin/python app/local_factory.py --scan-state --state NY --top-n 10
```

Stage 1 makes one LegiScan `getMasterList` call for the state's current session
and ranks bills without fetching any text:

* Keeps status 1 to 4 (Introduced, Engrossed, Enrolled, Passed).
* Drops a bill whose title or description contains a noise keyword
  (appropriations, budget, memorial, highway, bridge, license plate,
  congratulating, commemorating, school district). Matching ignores case.
* Scores title plus description by keyword weight, each keyword counted once:
  5 for artificial intelligence, algorithmic, automated decision, extended
  producer responsibility, impact assessment; 4 for biometric, privacy, consumer
  data, data broker, cybersecurity, emissions, greenhouse gas, supply chain, pay
  transparency, civil penalty; 3 for packaging, employer, disclosure, reporting,
  audit, attorney general, fiduciary; 2 for financial.
* Adds 3 when the score is above 0 and the bill is past introduction (status 2
  or more).
* Keeps scores of 4 or more, sorts by score then status (both highest first),
  and takes the top N.

Stage 2 runs each candidate through the single bill steps above, including the 70
and Z3 gate. A bill that fails (LegiScan, LLM, Postgres or OPA error) becomes an
`ERROR` row and the scan moves on. The output is a ranked matrix, highest
`opportunity_score_vs` first and errors last:

```text
rank  bill_uid      score  max fine  PRA  Z3 status                        action
1     CA_SB7_2140   82     $20,000   no   UNSAT_DETERMINISTIC_AND_COMPLETE  GREENLIT cartridges/ca_sb7_2140.rego
2     CA_AB12_2140  55     $7,500    yes  UNSAT_DETERMINISTIC_AND_COMPLETE  SKIPPED: opportunity_score_vs 55 < 70
3     CA_AB40                                                               ERROR: LiveBillError: LegiScan getBill returned HTTP 500
```

The scan exits 1 when any bill errored or a greenlit chain check failed, else 0.

| Variable | Default |
| --- | --- |
| `LEGISCAN_API_KEY` | none; required for `--bill`, `--bill-id` and `--scan-state` |
| `LLM_BASE_URL` | `http://localhost:11434/v1` (Ollama) |
| `LLM_MODEL` | `qwen2.5-coder:14b` |
| `OPENAI_API_KEY` | `ollama` |

Postgres and OPA come from the same variables as the dry run (`FACTORY_PG_PORT`,
`OPA_URL` or `FACTORY_OPA_PORT`). The LegiScan key is sent only as the API query
parameter. Error messages are rebuilt without the request URL, and the httpx
request log is raised to WARNING so the key is not printed.

This path skips human review on purpose, like the dry run. `pipeline.py approve`
does not accept these rules, because their package is `cartridge.<slug>` rather
than `factory.<slug>` and the stored Rego check fails.

`requirements.txt` is the editable spec; `requirements.lock` is generated from
it with hashes (`uv pip compile --universal --python-version 3.12
--generate-hashes requirements.txt -o requirements.lock`). Regenerate the lock
after editing `requirements.txt`.

## Sample lobbying graph (SAMPLE DATA)

```bash
./bootstrap.sh                              # once, so .env and the Neo4j container exist
.venv/bin/python app/seed_neo4j.py
```

**Everything in this graph is sample data.** The bill numbers (CO SB205, CT SB2,
TX HB1709, CA SB253), sponsors (Rodriguez, Maroney, Capriglione, Wiener) and
companies (Workday, HireVue, Upstart, Chevron) are real names. Every filing ID,
spend, lobbying position, `passage_probability`, `les_score`, `opportunity_score`,
model DNA similarity, committee link and lobbying firm is invented. Do not show
it to anyone as fact.

The script:

1. Loads `.env` from this directory with python-dotenv. Connection settings are
   `NEO4J_URI` (default `bolt://localhost:7687`, or the port in
   `FACTORY_NEO4J_BOLT_PORT`), `NEO4J_USER` (default `neo4j`) and
   `NEO4J_PASSWORD`. Without those two it splits `NEO4J_AUTH=neo4j/<password>`,
   which is how `.env.example` and `docker-compose.yml` set the auth.
2. Creates uniqueness constraints (`IF NOT EXISTS`) on `Bill.bill_uid`,
   `BillVersion.version_uid`, `Legislator.bioguide_or_os_id`,
   `Committee.committee_uid`, `Corporation.domain` and `LobbyingFirm.name`.
3. Writes every node and relationship with `MERGE`, so re running it does not
   duplicate anything. Each one carries `sample: true`.
4. Prints the buyer intent table, framed by a SAMPLE DATA banner: corporations
   whose lobbying firm worked a bill with `passage_probability >= 0.4`, where the
   retained position is `OPPOSE`, `AMEND` or `MONITOR`, highest spend first.

Relationships: `HAS_VERSION` and `MORPHED_INTO` (bill versions),
`SHARES_MODEL_DNA` (bill to bill), `SPONSORED`, `CHAIRS`, `REFERRED_TO`,
`RETAINED` (with `spend`, `filing_id`, `position`) and `LOBBIED_ON`.

Remove the sample data:

```cypher
MATCH (n {sample: true}) DETACH DELETE n
```

`tests/test_seed_neo4j.py` runs offline against a fake session. Its one live
test is marked `integration` and skips when Neo4j is not reachable.

## Keys

`ledger.py` creates `.keys/ed25519.pem` (mode 600) on first approve. `.keys/`
is gitignored. Losing the key means old receipts still verify with the public
key you kept, but new receipts start signing with a new key.

## Tests

```bash
.venv/bin/python -m pytest -m "not integration"   # offline, no services
.venv/bin/python -m pytest -m integration         # needs OPA + Postgres (+ Neo4j for the seed test) up
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
- Z3 checks the compliance_status logic built from the IR, not the generated Rego text.
  The two are kept in step by hand and by tests.
- `approve` marks the rule `human_verified` before deployment finishes. If OPA
  or an assertion fails afterwards, the flag stays true and no receipt is
  written.
- Compose default credentials are local dev values. Do not reuse them.
