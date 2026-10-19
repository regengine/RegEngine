# Jev Lab: a local Jev sandbox and a Claude ↔ Jev self-improving loop

**Status: experimental dev tooling.** Jev Lab runs on your own machine. It
never changes the production spine. It reads the production question sets,
measures rewrites of their wording, and records the results in a local ledger.
A rewrite that measures better reaches production only through a pull request
that a person reviews.

Code: `scripts/jev_lab/`. Tests: `services/ingestion/tests/test_jev_lab_*.py`.
Related: [Jev header mapping](JEV_HEADER_MAPPING.md), `scripts/jev_eval.py`,
`scripts/jev_ask.py`, `.claude/skills/jev-sidecar/SKILL.md`.

## Start it (macOS)

1. From the repo root, with the repo's virtualenv:

   ```bash
   venv/bin/python scripts/jev_lab serve --fake   # offline: nothing leaves the machine
   ```

   It prints a link such as `http://127.0.0.1:8204/#token=…` and opens it in
   your browser.

2. For live Jev, put the key in your own shell. Never put it in chat or in a
   file in the repo. One option is the macOS Keychain. Type these commands in
   your terminal; `-w` with no value prompts for the key without echoing it:

   ```bash
   security add-generic-password -s regengine-typesafe -a "$USER" -w
   export TYPESAFE_API_KEY="$(security find-generic-password -s regengine-typesafe -w)"
   venv/bin/python scripts/jev_lab serve
   ```

   `--prompt-key` reads the key from a hidden prompt for one run instead.

3. For the Claude side of the loop, the default backend is your local Claude
   Code CLI (`claude`), which uses its existing login. Alternatively, pass
   `--proposer anthropic-sdk`: run `pip install anthropic` in your own
   virtualenv and set `ANTHROPIC_API_KEY`. The `anthropic` package is not in
   `requirements.lock`.

If the key is missing and `--fake` is not set, every command exits with code
2 and sends nothing.

## What leaves the machine

| To | What | Never |
| --- | --- | --- |
| Jev (`api.typesafe.ai`) | Header rows of the labelled cases, header rows you paste into Header check, the state and questions you type in Ask Jev, and question wording. | Row values (`header_sample_values` is forced to 0), tenant ids, secrets |
| Claude | The training split's misses and uncertain answers (header names, labels, Jev's answers and confidence), the current wording, and a history that gives one bit per kind from the held-out check. | Held-out cases or their numbers, the API keys (stripped from the `claude` process environment), anything from Ask Jev |

The privacy guard (`scripts/jev_lab/privacy.py`) checks everything that goes
to Jev or Claude before it is sent. It refuses:

- secrets, and the value of any secret environment variable;
- emails, phone numbers, SSNs and street addresses;
- 13- and 14-digit GLN/GTIN numbers;
- UUIDs;
- header rows that look like rows of values.

It reports what it found by kind and location, never by value. It catches
mistakes. It does not prove that nothing sensitive remains, so paste header
rows and synthetic examples, not exports.

## The page

- **Ask Jev.** Typed questions (which of these, is this true, how much) about
  any state, all in one request. Answers come with the jev-sidecar confidence
  words: strong (0.90 or more), moderate (0.50 to 0.90), "Jev is unsure"
  (below 0.50). "Jev was right / wrong" buttons record your verdict in the
  ledger (the verdict only, not the question).
- **Header check.** Paste one header row to see the two questions
  `POST /api/v1/ingest/csv` asks, with production wording or the lab's
  current incumbent. Label the columns and the file CTE, then save the row.
  Labelled rows feed the loop: this is the human side of the feedback.
- **Loop.** Start, score only, or stop. The tab shows:
  - the request estimate;
  - gauges for Jev requests, held-out wear, Claude cost and Claude
    foresight;
  - Brier score per generation;
  - a reliability diagram;
  - the metrics table;
  - a plain-language log.
- **Ledger.** Every generation with Claude's rationale, the decision per
  question and the wording diff against production. Per rewrite there is a
  "Confirm on fresh rows" button.
- **Sky as table.** The same data the sky draws, one row per labelled
  subject.

### The sky

Every mark is one datum:

| Mark | Meaning |
| --- | --- |
| Star | One labelled subject: a header (Header fields) or a file (File CTE). Distance from Jev is `1 - confidence`. The dashed circles are the review and auto-apply thresholds. |
| Upper half / behind the veil | Training split / held-out split (never shown to Claude) |
| Filled dot, four-point spark | Right answer, wrong answer |
| Ring with dot, ring with slash | Declined (`no_match` / `mixed_or_unclear`), right or wrong |
| Red dashed halo | Wrong at auto-apply confidence: the case the gates veto |
| Small companion | The answer changed when the options were reversed |
| Line from a star | Where the current rewrite moves that subject (teal: fixed, red: broken) |
| Gold crown around Jev | Reliability per confidence bin: the arc is accuracy, the tick is mean confidence |
| Rings around Jev | Generations: gold kept, dashed rejected on held-out, dotted failed on training. A small sky shows only the latest rings that fit; the Loop tab's Brier chart has every generation |
| Moon and comets | Claude. It moves one step per generation, and each comet is a proposal, with one bead in its tail per changed option. A comet reaching Jev with a flash was kept. One falling to the veil failed the held-out check. One fading midway failed on training. One bursting at the moon was invalid, or Jev never judged it (Jev unavailable, or the run ended first). A dashed ring around the moon changed nothing. |
| Dots along the top | One per Ask Jev question since the server started. Brightness is how sure Jev was of the answer it gave (a confident "no" is as bright as a confident "yes"); colour is your verdict |

"Pause motion" and the system reduced-motion setting stop all animation: each
comet is drawn once at its ending, and nothing redraws until new data arrives.
The theme follows the system unless you pick one.

## The loop

1. **Cases.** The cases are:
   - the seven CSV templates;
   - `docs/engineering/examples/jev_eval_cases.json`;
   - rows labelled in Header check.

   The first run of a split epoch splits them by case into training and
   held-out sets, stratified by label so a rare label lands on both sides,
   and pins each case's side in `split.json`. A case added later is *fresh*:
   the loop leaves it out until you rotate the split, and `confirm` uses it.
   A labelled row with the same headers as an existing case is refused.
2. **Parity tripwire.** On the offline fake, the lab must score the
   production wording exactly as `scripts/jev_eval.py` does: same answers and
   same request bodies. Otherwise the run stops.
3. **Incumbent.** Jev answers every case with the current wording. The
   training split is asked a second time without the cache. How much the two
   answers differ, subject by subject, is Jev's noise floor:
   - the required held-out Brier gain is at least twice the noise's standard
     error at the held-out split's size;
   - the number of right answers that may turn wrong is what Jev's own
     answer-flip rate predicts (zero on the fake, which repeats itself
     exactly).
4. **Each generation:**
   1. Claude gets the training data. The brief is checked for held-out cases
      and held-out headers before it leaves.
   2. Claude returns a patch to the wording (`what`, `not_for`, `examples`,
      `task`, `guidance`) and the misses it predicts the patch will fix.
   3. The wording is refused if it renames, adds, drops or reorders an
      option, copies a training header into an example, stops explaining the
      state keys, or grows past 1.5 times production.
   4. **Training screen**, compared subject by subject. The Brier score must
      improve. No subject may become wrong, or start flipping when the
      options are reversed, at auto-apply confidence. No more right answers
      may turn wrong than the noise allows. A candidate that fails never
      touches the held-out split.
   5. **Held-out gate.** The same subject-by-subject checks, plus:
      - a Brier gain of at least the margin;
      - calibration error and the confidence of wrong answers do not grow
        past a small slack;
      - more subjects improve than worsen.

      A candidate that copies a held-out or fresh header into an example is
      turned away here. That costs a held-out look, and Claude sees the same
      "not kept" as for any rejection, so the check cannot reveal which
      headers are held out.
   6. **Foresight.** Claude's predicted fixes are scored on the training
      split and returned to it next generation. Jev's answers teach Claude
      the wording, and the hit rate tells Claude how well it reads Jev.
5. **Stops.** A run stops when any of these happens:
   - the generations are done;
   - three generations in a row are rejected;
   - the Jev request budget runs out;
   - the held-out split has judged 12 candidates per question, after which
     you rotate the split;
   - Jev stops answering (that is recorded as a Jev failure, never as a
     rejection, and costs no held-out look);
   - the split is rotated while the run is using it;
   - you press Stop.

"Confidence Brier" scores Jev's confidence as a forecast of "this answer is
right". The auto-apply and review bands depend on exactly that property.

The labelled set is small (22 cases, about 118 subjects), so most honest runs
keep little or nothing. "No improvement shown" is a valid result. Grow the
cases by labelling real header shapes in Header check, using synthetic
headers rather than customer data.

## Commands

```bash
venv/bin/python scripts/jev_lab serve [--fake] [--port 8204|0] [--proposer claude-cli|anthropic-sdk|offline]
venv/bin/python scripts/jev_lab loop  [--fake] --generations 5 [--margin 0.01] [--json]
venv/bin/python scripts/jev_lab score [--fake] [--json]
venv/bin/python scripts/jev_lab ledger
venv/bin/python scripts/jev_lab export <digest>|incumbent
venv/bin/python scripts/jev_lab confirm <digest> [--fake]
venv/bin/python scripts/jev_lab reset [--rotate-split]
```

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | done |
| 1 | bad usage |
| 2 | not configured, nothing sent |
| 3 | Jev unavailable |

`--max-jev-requests` (default 400) caps what one process sends. Identical
requests are answered from `jev-cache.jsonl` and cost nothing. Pass
`--no-cache` to re-send.

## Local state

Local state lives in `~/.regengine/jev-lab/` (override it with
`JEV_LAB_HOME` or `--home`). The directory is outside the repository and has
mode 0700. Runs judged by the offline fake keep everything except labelled
rows in `~/.regengine/jev-lab/fake/`. Wording the fake picked can never
become the live incumbent or use the live held-out split. `ledger`,
`export`, `confirm` and `reset` take `--fake` to read that ledger, and
`export` never offers fake-judged wording for promotion.

| File | Contents |
| --- | --- |
| `ledger.jsonl` | Generations, decisions, runs, noise floors, sandbox verdicts |
| `question_sets/<digest>.json` | The wording behind each digest |
| `split.json` | The split salt, each case's pinned side, held-out looks per question |
| `cases.local.json` | Rows labelled in Header check (headers and labels, with the first `labelled_at`); shared by both modes |
| `jev-cache.jsonl` | Jev answers keyed by a SHA-256 of the request; the request itself is not stored |

Never written: API keys, the page token, row values, Claude's transcript.

## Promotion

1. `venv/bin/python scripts/jev_lab export <digest>` prints three things:
   - the wording;
   - the diff against production;
   - the checklist below.
2. `venv/bin/python scripts/jev_lab confirm <digest>` checks the rewrite on
   *fresh* rows. Fresh rows were added after the current split was pinned,
   so no generation was selected on them. With fewer than 5 fresh subjects
   it says the data is insufficient.
3. Open a PR that applies the wording:
   - header mapping goes to `services/shared/jev/header_mapping.py`;
   - file CTE goes to `services/shared/jev/cte_classification.py`.
4. In the same PR, bump `QUESTIONS_VERSION` and update every pin. Find them
   with `grep -rn '<old version>' services docs`. The test suites pin the
   version strings in several places.
5. Run `python3 scripts/jev_eval.py` with the live key and attach its report.

## Local server security

- **Network binding.** It binds `127.0.0.1` only; there is no host option.
- **Token.** Every API call needs the per-process token. The page receives
  it in the URL fragment, which the browser never sends to a server, and
  keeps it in `sessionStorage`.
- **Host and Origin checks.**
  - `Host` must name the lab, which defends against DNS rebinding.
  - A cross-site `Origin` or `Sec-Fetch-Site` is refused.
  - A POST must carry the lab's own `Origin`.
  - No CORS headers are ever sent.
- **Page restrictions.** A strict Content-Security-Policy applies: the page's
  own script and stylesheet only, and requests only to the lab. The page
  cannot be framed.

## Always ready to answer

`serve` keeps running until Ctrl-C. It opens your browser through a
one-minute, owner-only redirect file in the lab directory, so the page token
never appears on a command line other users can see. To have it start at login, add a
LaunchAgent that runs the `serve` command from a shell that reads the key
from the Keychain, as in step 2. The plist itself must not contain the key.
The server never starts a loop on its own: every run is started by a person.
