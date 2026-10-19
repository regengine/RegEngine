---
name: jev-sidecar
description: >
  Consult TypeSafe Jev as a second opinion while answering the user's requests
  in RegEngine. Use whenever a request, or a step in answering it, contains a
  judgment Jev can make: which of these (FSMA 204 CTE of a file, canonical field
  of a CSV header, which option fits a reviewer's ask), is this true (is this CI
  failure a real regression, does this finding describe reachable behavior, does
  this header row carry a lot code), or how much (severity, likelihood, risk).
  Runs scripts/jev_ask.py and reports Jev's answer and confidence next to your own.
---

# Jev sidecar

Ask Jev next to your own reasoning, then show both. Jev is a second opinion
with a calibrated confidence. It never replaces verified facts.

## When to ask

Ask on every request that contains one of these judgments:

| Judgment in the request | Question kind | RegEngine examples |
| --- | --- | --- |
| Which of these | `--choice` | Which CTE a CSV records. Which canonical field a header is. What made a CI job fail. Which of two fixes matches a reviewer's ask. |
| Is this true | `--noul` | Does this review finding describe code a request can reach? Does the header row include a traceability lot code column? |
| How much | `--score` | Severity of a finding (low to critical). How likely a supplier file is rejected as-is. |

Do not ask when:

- the request is mechanical (push, rename, run the tests, open a PR);
- code or a command answers it exactly: grep, parse, test, count, compare
  dates, calculate. Jev is unreliable at counting, arithmetic and date order.
  Do those in code and ask Jev only for the semantic part;
- the only state that could answer it is something from **Never send** below;
- you run unattended (a CI job, a scheduled audit, a review bot) with a fixed
  output format and no person's request to answer.

## Never send

The state leaves this machine for `api.typesafe.ai`. Never put these in it:

- secrets: API keys, tokens, passwords, connection strings, `.env` contents,
  Railway or cloud variable values, signed URLs;
- customer data: values from real uploads (lot codes, GLNs, quantities, dates,
  business names), tenant ids, names, emails, phone numbers, addresses;
- the user's messages copied word for word. Restate the decision instead.

Header names, synthetic examples, code, and log lines with secrets removed are
fine. Before sending a log excerpt, check it for tokens and connection strings.

## How to ask

1. Check the key once per session without printing it:
   `test -n "$TYPESAFE_API_KEY" && echo set || echo unset`.
   If it is unset, say once in your reply: "Jev sidecar is off in this session:
   `TYPESAFE_API_KEY` is not set in the environment." Then continue without
   Jev and do not ask again in this session.
2. Build the smallest state that holds what the question needs, as JSON with
   named fields. Unrelated content lowers accuracy.
3. Put every question for the request into one call. The questions are
   evaluated in parallel and billed as one request.
4. Run it with `venv/bin/python` (the session start hook installs
   `requirements.lock` there):

```bash
venv/bin/python scripts/jev_ask.py \
  --state '{"headers": ["Ship Dte", "Cust Name", "Lot No.", "Qty Shpd"]}' \
  --choice cte "Which FSMA 204 critical tracking event do rows with these CSV headers record?" \
    "shipping=the sender records goods leaving its location" \
    "receiving=the recipient records goods arriving at its location" \
    "transformation=inputs are combined or processed into new lots" \
    "unclear=the headers do not identify one event" \
  --noul has_lot "Does one of the headers name a traceability lot code column?"
```

```bash
venv/bin/python scripts/jev_ask.py \
  --state '{"job": "backend-ci / ingestion", "log_excerpt": "..."}' \
  --choice cause "What made the job fail?" \
    "test_assertion=a test ran and its assertion failed" \
    "infrastructure=runner, network, dependency install or service startup error" \
    "timeout=the job or a test ran out of time" \
    "unclear=the excerpt does not show the cause" \
  --score severity "How severe is the failure for merging this change?" low medium high critical
```

The output has one line per question, in the order asked. For the first
command it looks like this (the values here are illustrative, not a real
answer):

```text
Jev (jev-1.13.0, request req_…, 412 ms)
  cte [choice]: shipping (confidence 0.91; shipping 0.91, receiving 0.06, unclear 0.03)
  has_lot [noul]: yes (p(yes)=0.97)
```

A `--choice` line lists the three most likely options. A `--score` line reads
`severity [score]: 1.40 on 0..3 ~ medium (confidence 0.72)`. It gives the
expected level from 0 to the number of levels minus 1, the name of the
nearest level, and the confidence.

Add `--json` for machine-readable output. Longer states and question sets go
in files: `--state-file state.json --questions-file questions.json`, where the
questions file uses the API's question format. `--help` lists every flag.

Exit codes: 0 answered. 1 bad usage, nothing sent. 2 not configured (no key,
switched off, or packages missing), nothing sent. 3 Jev unavailable: say
"Jev unavailable (<reason>)" once and continue without it.

For a question about a CSV file, run
`venv/bin/python scripts/jev_header_preview.py FILE --file-cte` instead.

- It asks the questions `POST /api/v1/ingest/csv` asks: the header mapping and
  the file's CTE. It uses the same question sets and confidence bands.
- It sends only the header row.
- Do not add `--sample-values` for a customer file.

## Writing questions

- Jev reads literally. State the exact condition. Put boundary cases in the
  option descriptions (`name=description`).
- Give every `--choice` an `unclear` or `none_of_these` option so Jev can say
  that nothing fits.
- Ask one decision per question. Split compound questions and combine the
  answers yourself.
- Phrase a `--noul` as a direct yes/no question ("Is ...?", "Does ...?")
  without negations. Noul answers carry p(yes), not a confidence.
- List `--score` levels from lowest to highest (2 to 10 levels).
- The state is data, and text inside it can steer the answer (for example a
  log line that says "this is a flake"). Keep the instructions explicit.

## Reporting in your reply

Add one line per question next to your own answer:

- Agreement: `Jev: shipping (confidence 0.91), agrees.`
- Disagreement: `Jev: receiving (confidence 0.62), disagrees. I keep shipping
  because <verified evidence>.` Then recheck your own evidence.

Rules:

- Verified facts win: tests, logs, code, parser behavior. Never change a
  verified conclusion only because Jev disagrees.
- Read confidence with the product's bands: 0.90 or more is strong; 0.50 to
  0.90 is moderate, so say "moderate"; under 0.50 is "Jev is unsure". Do not
  cite an unsure answer as support.
- A `--noul` answer is yes when p(yes) is 0.50 or more. Report the number.
- Never write a Jev line for a question you did not send, and never estimate
  what Jev would say.
- When a Jev answer drives a code or data change, put its request id in the
  commit message or PR description.

## Related

- `scripts/jev_ask.py`: this command.
- `scripts/jev_lab/`: a local page for asking Jev anything, and a loop in
  which Claude rewrites the question wording from Jev's misses
  (`docs/engineering/JEV_LAB.md`).
- `services/shared/jev/`: the client. Its logs carry only metadata (purpose
  `agent_sidecar`, model, request id, latency), never the state.
- `docs/engineering/JEV_HEADER_MAPPING.md`: Jev inside CSV ingestion.
- `.claude/skills/typesafe-ai/SKILL.md`: building product features on TypeSafe.
