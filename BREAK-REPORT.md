# Break report: plugins/

Summary: 1 break found, 1 fixed and tested, 0 fixed but failing, 0 blocked.

The plugins package is a fixed list of FDA reading sources, not a folder that loads arbitrary plugin files. The nightly regulation import trusted every row in that list.

## High: hostile catalog row was still fetched

What broke: `run_all_regulations_ingest` handed each row in `plugins/fsma/sources.py` to the scraper with no checks. A row could use a path-like name, a `file:` URL or any public website, a jurisdiction other than FDA, or extra fields such as `scopes`. The job still finished and reported jurisdiction FDA. Before the fix, a one-row catalog with name `../../etc/passwd`, URL `file:///etc/passwd`, and `scopes: ["admin"]` produced a completed job (`ingested: 1`) and one scrape call with that name and URL. Extra fields were ignored, so they did not grant those scopes, but the fetch still ran. A name that contains a colon would also confuse the manual-review queue, which stores `name:url` and splits on the first colon.

How to reproduce: import `app.routes_scraping`, replace `FSMA_SOURCES` with that hostile row, stub `discovery.scrape` so it records arguments, and call `run_all_regulations_ingest`. On the old code the stub is called. No production URL was contacted.

Root cause: `services/ingestion/app/routes_scraping.py:147` (`discovery.scrape` inside `run_all_regulations_ingest`). The guard now sits at `services/ingestion/app/routes_scraping.py:136`, and the rules live in `plugins/fsma/sources.py:124` (`load_fsma_sources`).

Fix: `load_fsma_sources` accepts only the fields name, url, type, jurisdiction, and description. The name must be a short token with no path pieces, colons, or `..`. The type must be html or pdf. The jurisdiction must be FDA. The URL must be https, must not carry a username or password, must not walk upward with `..`, and the host must be ecfr.gov, fda.gov, federalregister.gov, or a subdomain of those. An empty list, a non-list, a duplicate name, or an unknown field is refused. The ingest job runs this check before any scrape. The eight shipped sources still load.

Test results: `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_fsma_plugin_catalog.py services/ingestion/tests/test_routes_scraping_1342.py services/ingestion/tests/test_routes_scraping_task_queue.py --tb=short` finished with `55 passed in 1.80s`. `.venv/bin/ruff check` on the touched files reported `All checks passed`. The old behavior was confirmed first, with the stub scrape call shown above, before the checker existed.

## Open questions

Redirects after the first request are still allowed when the next address is a public host. They are not limited to the three FDA source domains. I did not change that, and I did not request the live FDA pages.

The manual-review queue format is still `name:url`. Plugin names can no longer contain a colon. Any other caller that passes a colon in the name can still scramble the split.

`run_all_regulations_ingest` still does not pass the caller's tenant id into the scraper, so a robots denial is queued under the tenant name `system`. That is outside this plugin change.

There is no on-disk manifest file and no directory loader. Putting a new `.py` file in `plugins/` does nothing until some module imports it. I did not add a loader.
