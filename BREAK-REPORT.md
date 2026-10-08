# BREAK-REPORT: services/nlp break-it pass (Oct 8, 2026)

## Summary

Probed malformed text, empty docs, huge docs, encoding traps, and
classification boundary labels across the NLP subsystem (legacy regex
extractor, signal classifier, query planner, entity resolver, FSMA
extractor). Local tests only, no production calls.

Result: 3 breaks found, all 3 fixed and tested. 0 fixed but failing.
0 blocked. 9 new regression tests pass, full services/nlp/tests suite
passes, ruff clean on all touched files.

## Finding 1 (high): org-name regex stalls the worker on long word runs

What broke: `extract_entities` on a document containing a long run of plain
words with no corporate suffix took 9.2 seconds at 4000 words and scaled
worse than quadratically (500 words: 0.06 s, 1000: 0.27 s, 2000: 1.4 s,
4000: 9.2 s). A multi-MB document, which the loader permits up to 25 MB,
would stall the extraction worker far beyond any timeout. Any lowercase
words trigger it because the pattern is case-insensitive.

How to reproduce: `extract_entities("word " * 4000 + "!")` and time it.

Root cause: services/nlp/app/extractor.py:23. `ORGANIZATION_PATTERN` used an
unbounded inner repetition `(?:\s+[A-Z][\w&'\.]+)*` ahead of a required
corporate suffix, so every failure backtracked over all partitions of the
word run. Reachable in production: server/workers/task_processor.py runs
`extract_entities` on task text.

Fix: bounded the inner run to `{0,5}` (six-word names max). Verified the
bounded pattern returns identical matches on real names ("Tyson Foods,
Inc.", "Walmart Inc.", "Acme Fresh Produce Distribution Company LLC",
"Ralphs Grocery Company", "Taylor Fresh Foods, Inc.") and runs linear
(20000 words in 0.04 s vs about 0.27 s at 1000 words before).

Test results: new `TestOrgPatternComplexity` (2 tests) passes; full
services/nlp/tests suite passes.

## Finding 2 (medium): 2000-digit number becomes inf in threshold entities

What broke: `extract_entities("Limit is " + "9"*2000 + " percent.")`
emitted a THRESHOLD entity with value `inf`, which serializes as
nonstandard JSON and can poison numeric columns downstream.

How to reproduce: extract thresholds from the text above and check
`math.isfinite(entity["attrs"]["value"])`.

Root cause: services/nlp/app/extractor.py:323 (threshold loop). `float()`
of a huge digit run overflows to inf and the value was stored unchecked.

Fix: skip threshold entities whose parsed value is not finite. No real
threshold looks like that, so dropping the entity is safer than storing
a fabricated cap.

Test results: new `TestThresholdFinite` passes; confirmed the old code
emitted `inf` for the same input.

## Finding 3 (low): None and non-string input crash with AttributeError

What broke: `SignalClassifier.classify_signal(None)`,
`infer_obligation_type(None)`, `parse_query(None)`, and
`FSMAExtractor.extract(None)` each raised bare `AttributeError`
(`'NoneType' object has no attribute 'lower'`), and non-string types
failed the same way. Empty and whitespace documents were already fine
(UNCATEGORIZED / UNKNOWN with review required).

How to reproduce: call any of the four with None.

Root cause: services/nlp/app/classification.py:41,
services/nlp/app/extractor.py:177 (obligation) and :291 (entities, already
guarded), services/nlp/app/query_planner.py:75,
services/nlp/app/extractors/fsma_extractor/extractor.py:132. No input
type check before calling string methods.

Fix: each entry point now raises `TypeError` with a clear message for
non-string input, matching the existing `extract_entities` precedent that
a missing document must fail loudly instead of reading as "processed OK,
nothing found". Empty-string behavior is unchanged.

Test results: new `TestInputTypeGuards` (6 tests) passes; confirmed the
old code raised AttributeError for each case.

## Probed and found safe (no change)

Encoding traps: null bytes, lone surrogates, BOM, RTL marks, emoji, and
tabs/newlines all extract without errors. Huge digit runs convert fast
(no float-parsing DoS). Threshold at 305 digits stays finite and valid.
`EntityResolver.resolve_organization` already returns None for None,
empty, whitespace, and non-string input. FSMA `extract` on empty and
whitespace text returns UNKNOWN with review required. `parse_query`
limit bounds are enforced by pydantic. Query API scope checks and the
text loader size/MIME/strict-decode caps were already hardened with
tests. Classification ties resolve to the first category, which errs
toward the highest risk rating; left as is (see open questions).

## Open questions

1. Should a classification tie (equal signal counts in two or more
categories) return UNCATEGORIZED instead of the first-listed category?
Current behavior errs toward HIGH risk, which seems deliberate for a
safety classifier, so no change was made. C.Lee decision needed before
any change here.
2. The org pattern over-matches across conjunctions (for example,
"Walmart Inc. and The Kroger Co" matches as one entity). Pre-existing
behavior, unchanged by this fix. Worth a separate finding if entity
precision matters downstream.
