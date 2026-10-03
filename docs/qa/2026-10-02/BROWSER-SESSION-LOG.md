
- **2026-10-03T02:02:51.164723+00:00** `local-server-preflight` — `python3 -c 'import urllib.request; from pathlib import Path; print(Path("docs/qa/2026-10-02/artifacts/browser/followup-server-metadata.txt").read_text()); op=urllib.request.build_opener(urllib.request.ProxyHandler({})); [(print(route, op.open("http://127.0.0.1:3114"+route).status)) for route in ["/", "/tools/scan", "/fsma/field-capture"]]'`; cwd `.`; exit 0, 0.22s. [Output](artifacts/browser/20261003T020251.164723Z-local-server-preflight.txt).

- **2026-10-03T02:02:58.254329+00:00** `browser-ux-axe-install` — `npm install --prefix /private/tmp/regengine-browser-ux-tools --no-audit --no-fund --ignore-scripts @axe-core/playwright@4.10.2`; cwd `.`; exit 1, 0.08s. [Output](artifacts/browser/20261003T020258.254329Z-browser-ux-axe-install.txt).

- **2026-10-03T02:03:05.540194+00:00** `browser-ux-axe-install-retry` — `env NPM_CONFIG_USERCONFIG=/private/tmp/regengine-browser-ux-tools/empty-npm-user NPM_CONFIG_GLOBALCONFIG=/private/tmp/regengine-browser-ux-tools/empty-npm-global npm install --prefix /private/tmp/regengine-browser-ux-tools --no-audit --no-fund --ignore-scripts @axe-core/playwright`; cwd `.`; exit 1, 0.39s. [Output](artifacts/browser/20261003T020305.540194Z-browser-ux-axe-install-retry.txt).

- **2026-10-03T02:03:09.328083+00:00** `browser-ux-axe-install-local-cache` — `env NPM_CONFIG_USERCONFIG=/private/tmp/regengine-browser-ux-tools/empty-npm-user NPM_CONFIG_GLOBALCONFIG=/private/tmp/regengine-browser-ux-tools/empty-npm-global npm install --cache /private/tmp/regengine-browser-ux-tools/npm-cache --prefix /private/tmp/regengine-browser-ux-tools --no-audit --no-fund --ignore-scripts @axe-core/playwright`; cwd `.`; exit 0, 1.27s. [Output](artifacts/browser/20261003T020309.328083Z-browser-ux-axe-install-local-cache.txt).

- **2026-10-03T02:03:33.193469+00:00** `existing-e2e-stock-local-attempt` — `env CI= NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/existing-e2e-safety.cjs PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ node node_modules/playwright/cli.js test --config=playwright.config.ts --project=chromium --reporter=list`; cwd `frontend`; exit 1, 0.30s. [Output](artifacts/browser/20261003T020333.193469Z-existing-e2e-stock-local-attempt.txt).

- **2026-10-03T02:03:38.645294+00:00** `existing-e2e-local-browser-suite` — `env CI= NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/existing-e2e-safety.cjs PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ QA_E2E_RUN=local-browser node node_modules/playwright/cli.js test --config=../docs/qa/2026-10-02/scripts/existing-e2e.config.cjs`; cwd `frontend`; exit 1, 129.78s. [Output](artifacts/browser/20261003T020338.645294Z-existing-e2e-local-browser-suite.txt).

- **2026-10-03T02:06:07.365599+00:00** `fe-regressions-chromium` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ QA_FE_RESULTS=docs/qa/2026-10-02/artifacts/browser/fe-regression-chromium-second-run.json node frontend/node_modules/playwright/cli.js test --config frontend/tests/e2e/qa-2026-10-02/fe-regressions.config.ts --project=chromium`; cwd `.`; exit 1, 13.25s. [Output](artifacts/browser/20261003T020607.365599Z-fe-regressions-chromium.txt).

- **2026-10-03T02:06:40.217596+00:00** `browser-ux-form-state-retry` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/node-isolation.cjs node docs/qa/2026-10-02/scripts/browser-ux-followup.cjs states`; cwd `.`; exit 0, 12.15s. [Output](artifacts/browser/20261003T020640.217596Z-browser-ux-form-state-retry.txt).

- **2026-10-03T02:06:35.538676+00:00** `browser-ux-keyboard-settled-retry` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/node-isolation.cjs node docs/qa/2026-10-02/scripts/browser-ux-followup.cjs keyboard`; cwd `.`; exit 0, 25.96s. [Output](artifacts/browser/20261003T020635.538676Z-browser-ux-keyboard-settled-retry.txt).

- **2026-10-03T02:04:47.829375+00:00** `browser-ux-three-engine-audit` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/node-isolation.cjs node docs/qa/2026-10-02/scripts/browser-ux-followup.cjs`; cwd `.`; exit 0, 147.72s. [Output](artifacts/browser/20261003T020447.829375Z-browser-ux-three-engine-audit.txt).

- **2026-10-03T02:07:13.095460+00:00** `fe-regressions-chromium-third` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ QA_FE_RESULTS=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/artifacts/browser/fe-regression-chromium-third-run.json node frontend/node_modules/playwright/cli.js test --config frontend/tests/e2e/qa-2026-10-02/fe-regressions.config.ts --project=chromium`; cwd `.`; exit 0, 5.11s. [Output](artifacts/browser/20261003T020713.095460Z-fe-regressions-chromium-third.txt).

- **2026-10-03T02:07:31.224584+00:00** `fe-regressions-all-engines` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ node frontend/node_modules/playwright/cli.js test --config frontend/tests/e2e/qa-2026-10-02/fe-regressions.config.ts`; cwd `.`; exit 1, 20.87s. [Output](artifacts/browser/20261003T020731.224584Z-fe-regressions-all-engines.txt).

- **2026-10-03T02:07:59.815018+00:00** `browser-ux-error-state-visible-alerts` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/node-isolation.cjs node docs/qa/2026-10-02/scripts/browser-ux-followup.cjs states`; cwd `.`; exit 0, 12.03s. [Output](artifacts/browser/20261003T020759.815018Z-browser-ux-error-state-visible-alerts.txt).

- **2026-10-03T02:08:01.222484+00:00** `existing-e2e-tour-settling` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ node docs/qa/2026-10-02/scripts/existing-e2e-tour-probe.cjs`; cwd `.`; exit 0, 26.16s. [Output](artifacts/browser/20261003T020801.222484Z-existing-e2e-tour-settling.txt).

- **2026-10-03T02:07:59.815009+00:00** `browser-ux-keyboard-platform-and-activation` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/node-isolation.cjs node docs/qa/2026-10-02/scripts/browser-ux-followup.cjs keyboard`; cwd `.`; exit 0, 28.19s. [Output](artifacts/browser/20261003T020759.815009Z-browser-ux-keyboard-platform-and-activation.txt).

- **2026-10-03T02:06:10.930546+00:00** `existing-e2e-final-local-browser-suite` — `env CI= NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/existing-e2e-safety.cjs PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ PLAYWRIGHT_BASE_URL=http://127.0.0.1:3114 QA_E2E_RUN=final-local-browser node node_modules/playwright/cli.js test --config=../docs/qa/2026-10-02/scripts/existing-e2e.config.cjs`; cwd `frontend`; exit 1, 138.49s. [Output](artifacts/browser/20261003T020610.930546Z-existing-e2e-final-local-browser-suite.txt).

- **2026-10-03T02:08:26.563458+00:00** `fe-regressions-crossbrowser-rerun` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ node frontend/node_modules/playwright/cli.js test --config frontend/tests/e2e/qa-2026-10-02/fe-regressions.config.ts --project=firefox --project=webkit`; cwd `.`; exit 1, 5.45s. [Output](artifacts/browser/20261003T020826.563458Z-fe-regressions-crossbrowser-rerun.txt).

- **2026-10-03T02:09:07.339707+00:00** `fe004-webkit-write-diagnostic` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ node frontend/node_modules/playwright/cli.js test --config frontend/tests/e2e/qa-2026-10-02/fe-regressions.config.ts --project=webkit --grep FE-004`; cwd `.`; exit 1, 1.00s. [Output](artifacts/browser/20261003T020907.339707Z-fe004-webkit-write-diagnostic.txt).

- **2026-10-03T02:09:48.277722+00:00** `browser-ux-harness-syntax` — `node --check docs/qa/2026-10-02/scripts/browser-ux-followup.cjs`; cwd `.`; exit 0, 0.03s. [Output](artifacts/browser/20261003T020948.277722Z-browser-ux-harness-syntax.txt).

- **2026-10-03T02:09:55.397348+00:00** `fe-regressions-final-all-engines` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ node frontend/node_modules/playwright/cli.js test --config frontend/tests/e2e/qa-2026-10-02/fe-regressions.config.ts`; cwd `.`; exit 0, 7.88s. [Output](artifacts/browser/20261003T020955.397348Z-fe-regressions-final-all-engines.txt).

- **2026-10-03T02:12:02.225387+00:00** `stop-followup-server` — `python3 -c 'from pathlib import Path; data=Path("docs/qa/2026-10-02/artifacts/browser/followup-server-metadata.txt").read_text(); stop=next(line.split("=",1)[1] for line in data.splitlines() if line.startswith("StopFile=")); Path(stop).touch(); print("Requested cooperative shutdown of this follow-up server only")'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/browser/20261003T021202.225387Z-stop-followup-server.txt).

- **2026-10-03T02:02:45.805249+00:00** `followup-built-server` — `python3 docs/qa/2026-10-02/scripts/browser-followup-server.py`; cwd `.`; exit 0, 556.51s. [Output](artifacts/browser/20261003T020245.805249Z-followup-built-server.txt).

- **2026-10-03T02:12:10.494615+00:00** `followup-listener-readback` — `python3 -c 'import socket; from pathlib import Path; print("Checking only loopback QA listeners"); [(print(port, "open" if socket.socket().connect_ex(("127.0.0.1",port))==0 else "closed")) for port in [3102,3114,3950]]; print("3950 belongs to the orchestrator and is deliberately retained")'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/browser/20261003T021210.494615Z-followup-listener-readback.txt).

- **2026-10-03T02:12:21.609949+00:00** `followup-artifact-inventory` — `python3 -c 'from pathlib import Path; p=Path("docs/qa/2026-10-02/artifacts/browser"); f=[x for x in p.rglob("*") if x.is_file()]; print("Files",len(f),"Bytes",sum(x.stat().st_size for x in f)); print("PNG files",sum(x.suffix==".png" for x in f)); print("Largest:"); [(print(x.stat().st_size,x.relative_to(p))) for x in sorted(f,key=lambda x:x.stat().st_size,reverse=True)[:5]]'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/browser/20261003T021221.609949Z-followup-artifact-inventory.txt).

- **2026-10-03T02:15:38.799768+00:00** `existing-e2e-proxy-tour-settling` — `env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ QA_E2E_RUN=proxy node docs/qa/2026-10-02/scripts/existing-e2e-tour-probe.cjs`; cwd `.`; exit 0, 26.28s. [Output](artifacts/browser/20261003T021538.799768Z-existing-e2e-proxy-tour-settling.txt).

- **2026-10-03T02:15:32.827337+00:00** `existing-e2e-proxy-local-browser-suite` — `env CI= NODE_OPTIONS=--require=/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine/docs/qa/2026-10-02/scripts/existing-e2e-safety.cjs PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ PLAYWRIGHT_BASE_URL=http://127.0.0.1:3115 QA_E2E_RUN=proxy-local-browser node node_modules/playwright/cli.js test --config=../docs/qa/2026-10-02/scripts/existing-e2e.config.cjs`; cwd `frontend`; exit 1, 139.40s. [Output](artifacts/browser/20261003T021532.827337Z-existing-e2e-proxy-local-browser-suite.txt).

- **2026-10-03T02:15:31.650153+00:00** `existing-e2e-per-hop-proxy-server` — `python3 docs/qa/2026-10-02/scripts/existing-e2e-proxy.py`; cwd `.`; exit 0, 165.10s. [Output](artifacts/browser/20261003T021531.650153Z-existing-e2e-per-hop-proxy-server.txt).

- **2026-10-03T02:19:21.829814+00:00** `stop-followup-rerun-server` — `python3 -c 'from pathlib import Path; files=sorted(Path("docs/qa/2026-10-02/artifacts/browser").glob("followup-server-*-metadata.txt")); p=files[-1]; data=p.read_text(); stop=next(line.split("=",1)[1] for line in data.splitlines() if line.startswith("StopFile=")); Path(stop).touch(); print("Requested cooperative stop using",p.name)'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/browser/20261003T021921.829814Z-stop-followup-rerun-server.txt).

- **2026-10-03T02:13:54.515496+00:00** `followup-built-server-redirect-rerun` — `python3 docs/qa/2026-10-02/scripts/browser-followup-server.py`; cwd `.`; exit 0, 327.41s. [Output](artifacts/browser/20261003T021354.515496Z-followup-built-server-redirect-rerun.txt).

- **2026-10-03T02:19:59.581784+00:00** `final-browser-handoff-validation` — `python3 -c 'from pathlib import Path
from collections import Counter
import json, re, struct, subprocess
root = Path.cwd()
qa = root / "docs/qa/2026-10-02"
def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()
assert git("branch", "--show-current") == "qa/2026-10-02-sweep"
assert git("rev-parse", "HEAD").startswith("c98e1a30")
required = ["PLAN.md", "SESSION-LOG.md", "FINDINGS.md", "COVERAGE.md", "SUMMARY.md"]
for name in required:
    text = (qa / name).read_text()
    assert text.count("## Browser follow-up pass") == 1, name
    assert "PR: opened by orchestrator" in text and "CI status: pending at time of writing" in text
rows = []
for line in (qa / "FINDINGS.md").read_text().splitlines():
    if re.match(r"\| (?:BE|FE|UX)-\d{3} \|", line):
        cells = [x.strip() for x in line.strip("|").split("|")]
        assert len(cells) == 9 and all(cells)
        rows.append(cells)
assert len(rows) == len({r[0] for r in rows}) == 18
counts = Counter(r[1] for r in rows)
expected_line = "Counts: " + " ".join(f"{s}={counts[s]}" for s in ["Critical","High","Medium","Low"])
summary = (qa / "SUMMARY.md").read_text()
assert re.findall(r"^Counts:.*$", summary, re.M) == [expected_line]
assert expected_line == "Counts: Critical=0 High=3 Medium=11 Low=4"
tracked = set(git("diff", "--name-only", "HEAD").splitlines())
assert tracked <= {"docs/qa/2026-10-02/" + f for f in required}, tracked
assert not git("diff", "--name-only", "--diff-filter=D", "HEAD")
changed = tracked | set(git("ls-files", "--others", "--exclude-standard").splitlines())
allowed = ("docs/qa/2026-10-02/", "frontend/tests/e2e/qa-2026-10-02/")
assert all(p.startswith(allowed) for p in changed)
assert len(list((root/"frontend/tests/e2e/qa-2026-10-02").glob("*.spec.ts"))) == 2
link_count = 0
for p in [qa / f for f in required] + list((qa/"artifacts/browser").glob("*.md")):
    text = p.read_text()
    if p.name in required:
        text = text.split("## Browser follow-up pass", 1)[1]
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
        target = target.split("#",1)[0].strip("<>")
        if not target or re.match(r"^[a-z]+:", target):
            continue
        assert (p.parent/target).exists(), (p.name, target)
        link_count += 1
art = qa/"artifacts/browser"
reg = json.loads((art/"fe-regression-results-2026-10-03T02-09-55-607Z.json").read_text())
assert [reg["stats"][k] for k in ["expected","unexpected","skipped"]] == [5,0,1]
assert not reg["errors"]
e2e = json.loads((art/"existing-e2e-proxy-local-browser-summary.json").read_text())
assert len(e2e["tests"]) == 270
assert [(p["project"],p["passed"],p["failed"],p["skipped"]) for p in e2e["projects"]] == [
    ("chromium",21,8,61),("firefox",20,9,61),("webkit",18,11,61)]
failure_classes = Counter(t["classification"].split(":")[0] for t in e2e["tests"] if t["status"] in ["failed","timedOut"])
assert failure_classes == {"environment":19,"harness":8,"product":1}, failure_classes
ux = json.loads((art/"browser-ux-summary.json").read_text())
assert len(ux["routes"]) == 42
for route in ux["routes"]:
    assert route["httpStatus"] == 200 and route["topLevel"]
    assert not route["pageErrors"] and not route["horizontalOverflow"]
    png = (art/route["screenshot"]).read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    dims = struct.unpack(">II", png[16:24])
    assert dims == (route["viewport"]["width"],route["viewport"]["height"])
    assert dims in [(1440,900),(390,844)]
oversized = [p.relative_to(art).as_posix() for p in art.rglob("*") if p.is_file() and p.stat().st_size > 5_000_000]
assert not oversized, oversized
subprocess.run(["git","diff","--check"],check=True)
print(expected_line)
print("PASS: five follow-up docs; 18 unique finding IDs; exact count line;", link_count, "local links")
print("PASS: 270 original cases; 19 environment / 8 harness / 1 product failures")
print("PASS: 5 expected regression failures / 1 environment skip; 42 true viewport PNGs")
print("PASS: original product/tests/artifacts preserved; only authorized docs/new QA tests changed")
print("PASS: no deletions, no artifact over 5 MB, git diff --check")
print("Branch",git("branch","--show-current"),"HEAD",git("rev-parse","HEAD"))
print("Changed/untracked files",len(changed))
print("This validates local browser evidence only; PR/CI and secret scan remain orchestrator-owned.")
'`; cwd `.`; exit 1, 0.13s. [Output](artifacts/browser/20261003T021959.581784Z-final-browser-handoff-validation.txt).

- **2026-10-03T02:19:59.765139+00:00** `final-browser-listener-readback` — `python3 -c 'import socket; print("Local QA listeners:"); [(print(port, "open" if socket.socket().connect_ex(("127.0.0.1",port))==0 else "closed")) for port in [3102,3114,3115,3950]]; print("Orchestrator browser server3950 retained; no action on historical PID")'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/browser/20261003T021959.765139Z-final-browser-listener-readback.txt).

- **2026-10-03T02:20:21.002379+00:00** `final-browser-handoff-validation-nul-paths` — `python3 -c 'from pathlib import Path; import shlex; p=Path("docs/qa/2026-10-02/artifacts/browser/20261003T021959.581784Z-final-browser-handoff-validation.txt"); command=p.read_text().split("Command: ",1)[1].split("\nExit:",1)[0]; code=shlex.split(command)[2]; old="set(git(\"ls-files\", \"--others\", \"--exclude-standard\").splitlines())"; new="set(filter(None, subprocess.check_output([\"git\", \"ls-files\", \"--others\", \"--exclude-standard\", \"-z\"], text=True).split(\"\\0\")))"; assert old in code; print("Validator retry uses NUL-delimited paths for Unicode Playwright test names"); exec(compile(code.replace(old,new), "<qa-handoff-validator>", "exec"))'`; cwd `.`; exit 1, 0.12s. [Output](artifacts/browser/20261003T022021.002379Z-final-browser-handoff-validation-nul-paths.txt).

- **2026-10-03T02:20:30.966307+00:00** `final-browser-handoff-validation-corrected` — `python3 -c 'from pathlib import Path; import shlex; p=Path("docs/qa/2026-10-02/artifacts/browser/20261003T021959.581784Z-final-browser-handoff-validation.txt"); command=p.read_text().split("Command: ",1)[1].split("\nExit:",1)[0]; code=shlex.split(command)[2]; old="set(git(\"ls-files\", \"--others\", \"--exclude-standard\").splitlines())"; new="set(filter(None, subprocess.check_output([\"git\", \"ls-files\", \"--others\", \"--exclude-standard\", \"-z\"], text=True).split(\"\\0\")))"; assert old in code; code=code.replace(old,new); oldclass="t[\"classification\"].split(\":\")[0]"; assert oldclass in code; code=code.replace(oldclass,oldclass+".split()[0]"); print("Validator normalizes NUL-delimited Git paths and the product UX-008 classification label"); exec(compile(code,"<qa-handoff-validator>","exec"))'`; cwd `.`; exit 0, 0.21s. [Output](artifacts/browser/20261003T022030.966307Z-final-browser-handoff-validation-corrected.txt).
