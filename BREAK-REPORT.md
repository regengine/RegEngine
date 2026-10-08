# Break report: graph exporters, fsma utils, hierarchy builder

## Summary

6 breaks found. 6 fixed and tested. 0 fixed but failing. 0 blocked.

Empty traces were checked and left as they are. An empty trace returns no CSV rows and a blank total. That is covered by tests and is not a break.

## High

### 1. A trace counted the same lot on every path, and text quantity aborted the export

What broke: A two-lot chain (LOT-A, one event, LOT-B, a second event) came back as 5 lots, 4 events, and a total quantity of 200. The real totals are 2 lots, 2 events, and 80. A quantity stored as text (`=1+1`, `40`, or `not-a-number`) raised `TypeError: unsupported operand type(s) for +=: 'float' and 'str'`. The compliance export catches that and returns HTTP 500.

How to reproduce: Build the linear chain in `services/graph/tests/test_break_graph_exports.py` (`test_multi_path_trace_counts_each_lot_once` and `test_non_numeric_quantity_does_not_abort_the_trace`) and call `trace_forward`. Before the fix the log line was `trace_forward_completed lots=5 events=4`.

Root cause: `services/graph/app/fsma/tracer.py`. The path query uses `WITH DISTINCT node, path`, so the same node is returned on every path that contains it. The old loop (trace_forward around line 299, trace_backward around line 602) added `quantity` on every row. The fix now adds at `tracer.py:263` inside `_take_path_node` (`tracer.py:205`), using `_quantity_parts` (`tracer.py:143`). Both `trace_forward` (`tracer.py:316`) and `trace_backward` (`tracer.py:599`) use that helper.

Fix: Remember each lot by its code, each event by its id, and add the quantity on the first sighting only. The longest hop is still kept when the same node shows up again. Numbers and numeric strings are added. Booleans, blanks, non-numeric text, NaN, and infinities add nothing. Non-numeric text stays on the lot so the CSV can still show it.

Test results: The new tests failed before the fix (`assert 5 == 2`, and `TypeError` at the old line 299). After the fix they pass. See the command at the end.

## Medium

### 2. The facility follow-up listed the same place twice

What broke: A facility already found on the path was appended again when the follow-up query returned the same GLN inside a larger property bag. A recall contact list then named that facility twice.

How to reproduce: `test_same_facility_is_not_listed_twice_when_the_follow_up_query_repeats_it`. Before the fix, `len(facilities)` was 2.

Root cause: `services/graph/app/fsma/tracer.py`, previously the membership test around line 335 (forward) and line 647 (backward). It compared the full Neo4j property dict to the slim dict already stored, so the check almost always missed. The new check is `_take_follow_up_facility` at `tracer.py:274`. The tenant check still runs before the skip, so a later cross-tenant copy of the same GLN still raises.

Fix: Key facilities by GLN, or by name plus address when there is no GLN. Share that set between the path loop and the follow-up query.

Test results: Failed before the fix (`assert 2 == 1`). Passes after.

### 3. A bad path row aborted the whole trace

What broke: A path row that was not a record (`"not-a-record"`) or a lot whose properties were null raised `TypeError` (`string indices must be integers` at the old line 253). The export then failed.

How to reproduce: `test_null_node_properties_do_not_abort_an_empty_trace`.

Root cause: `services/graph/app/fsma/tracer.py`, old `record["labels"]` / `props.get` in both path loops. The guard is `_path_row` at `tracer.py:116`.

Fix: Skip a row that cannot be read. Treat a null property bag as empty. An empty trace still returns a total of null.

Test results: Failed before the fix with `TypeError`. Passes after.

### 4. A download name could leave the folder after decoding

What broke: `header_filename("../../etc/passwd")` and the same shape in `rfc5987_filename` survived as a value that, after one percent-decode, resolved to `/private/etc/passwd`. The same happened for `/etc/passwd`, `foo/../../etc/passwd`, and `reports/../../../tmp/secret.csv`.

How to reproduce: `test_header_filename_cannot_escape_after_decode` and `test_rfc5987_filename_cannot_escape_after_decode`. Join the decoded name onto a directory and resolve it.

Root cause: `services/graph/app/exporters/safe_text.py`. The old `header_filename` (previously around line 102) percent-encoded the whole string and never reduced it to a file name. `..` was left in place. The fix is `_download_basename` at `safe_text.py:95`, used by `header_filename` (`safe_text.py:117`) and `rfc5987_filename` (`safe_text.py:138`).

Fix: Decode up to three times, strip controls, split on slash, backslash, and the common Unicode slashes, then keep the last segment. Drop `.` and `..`. Then apply the existing percent-encoding.

This is latent on today's export routes. Lot codes and dates are checked by patterns that do not allow a raw slash, so a request cannot currently pass `../` into the helper. The helper is still the boundary if a later caller passes a slash. Some already-encoded forms did not leave the folder after one decode of the old quoted value, because quoting encoded `%` again. Those forms are still reduced to the last segment so a later decode cannot bring `..` back.

Test results: Before the fix, raw `../` names resolved outside the folder (`/private/etc/passwd`). After the fix the names stay inside. The assertion resolves `/tmp` to `/private/tmp` before comparing, which is required on macOS. Re-running the old quoting algorithm against that comparison still escapes for `../../etc/passwd`.

### 5. A city code was not linked up to its country, and a looping parent was accepted

What broke: `build_jurisdiction_hierarchy(["US-CA-SF"])` wrote only the edge `(US-CA, US-CA-SF)`. The country edge `(US, US-CA)` was missing, so a leaf-only taxonomy was an orphan branch. A parent function that pointed AAAA at BBBB and BBBB back at AAAA did not raise, and it did not hang.

How to reproduce: `test_leaf_jurisdiction_is_linked_up_to_its_country` and `test_cyclic_parent_chain_is_rejected_before_any_write`.

Root cause: `services/graph/app/hierarchy_builder.py`. The old builder (previously around line 166) wrote only the immediate parent. The walk is now `_links_for` at `hierarchy_builder.py:114`. A repeat raises at line 130, before any `session.run`.

Fix: After the direct parent edge, also write ancestor edges whose child was not in the caller's input. `build(["US-CA"])` still makes 2 `session.run` calls, and `build(["", "US"])` still makes 1. A repeated parent, or a chain longer than 16 steps, raises `InvalidJurisdictionCodeError` and writes nothing.

The real `parent_code_for` cannot loop: each parent is a shorter code. The cycle test replaces that function so the new walk stays locked. It is not a loop that production data can hit today.

Test results: Before the fix the leaf assertion failed (`('US', 'US-CA')` was missing) and the cycle test reported `DID NOT RAISE`. Both pass after the fix. Existing hierarchy call-count tests still pass.

### 6. A non-dict row aborted the trace CSV and the recall CSV

What broke: A lot or association that was a string raised `AttributeError: 'str' object has no attribute 'get'` in `trace_csv.py` (old lines 82 and 110) and `recall_contacts_csv.py` (old line 105).

How to reproduce: `test_malformed_lot_does_not_abort_trace_csv`, `test_malformed_association_does_not_abort_trace_csv`, `test_malformed_association_does_not_abort_recall_contacts`.

Root cause: those `.get` calls assumed every item was a dict. Guards are now at `trace_csv.py:82` and `trace_csv.py:116`, and `recall_contacts_csv.py:107`.

Fix: Skip items that are not dicts. If a trace CSV was given associations and none of them are usable, fall through to the older one-row-per-event path instead of returning an empty file or crashing.

Test results: Failed before the fix with `AttributeError`. Pass after.

## Checked, not a break

- Empty trace CSV and empty recall list return no rows. The subject lot is not invented. Tests `test_empty_trace_csv_returns_no_rows` and `test_empty_recall_list_returns_no_rows` passed on the old code.
- Empty KDE completeness stays at rate 1.0 with trend `stable` when there are no events. That behavior is already tested in `test_data_quality.py` and was not changed.
- `traceability_linker` tenant checks were not touched.

## Tests

New file: `services/graph/tests/test_break_graph_exports.py`.

Before any production edit, this command exited 1. The progress line was `FFFFFFFFFFF.FFF..FFFFFFFF`: 22 failed, 3 passed.

```
~/metacode/fleet/heavy .venv/bin/pytest -q services/graph/tests/test_break_graph_exports.py --tb=line -p no:cacheprovider
```

The 3 passes were the plain file name and the two empty-graph locks. The 22 failures are the cases above.

After the fixes, the filename assertion was updated to resolve both paths. A separate check of the old quoting algorithm still sends `../../etc/passwd` to `/private/etc/passwd`, outside the folder.

Final command, exit 0:

```
~/metacode/fleet/heavy .venv/bin/pytest services/graph/tests/test_break_graph_exports.py services/graph/tests/test_exporters_safe_text.py services/graph/tests/test_trace_csv_rows_2945.py services/graph/tests/test_recall_contacts_csv.py services/graph/tests/test_trace_path_tenant_scope.py services/graph/tests/test_trace_backward_direction_2940.py tests/graph/test_hierarchy_builder_global_scope.py --tb=line -p no:cacheprovider
```

Result: `125 passed in 1.09s`.

Ruff, on the touched files, after the last test edit: `All checks passed`. Format check: already formatted.

## Open questions

- Empty KDE completeness reports rate 1.0 and trend `stable` when there are no events. The compliance score path treats an empty graph as unmeasured. Those two screens disagree. Left unchanged because the 1.0 behavior is an existing tested choice.
- Should a boolean quantity keep adding 0, or be rejected? It now adds 0. The old code added 1 because `True` is a number.
- A quantity such as `1,000` is not parsed. It adds 0 and the original text stays on the lot. European decimal commas were not guessed.
