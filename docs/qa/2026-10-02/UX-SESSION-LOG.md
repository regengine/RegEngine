
- **2026-10-03T00:36:34.080185+00:00** `orientation` — `python3 -c 'import os,pathlib,subprocess; print("cwd",os.getcwd()); [subprocess.run(c,check=False) for c in [["git","branch","--show-current"],["git","remote","get-url","origin"],["git","worktree","list"],["git","status","--short"]]]; [print("FILE",str(p),"\n",p.read_text()) for p in [pathlib.Path("frontend/AGENTS.md"),pathlib.Path("docs/qa/2026-10-02/META-SESSION-LOG.md"),pathlib.Path("docs/qa/2026-10-02/scripts/run_logged.py")] if p.exists()]'`; cwd `.`; exit 0, 0.12s. [Output](artifacts/ux/20261003T003634.080185Z-orientation.txt).

- **2026-10-03T00:37:06.795138+00:00** `local-runner-and-routes` — `python3 -c 'from pathlib import Path; import subprocess; files=["/Users/sellers/.codex/skills/playwright/SKILL.md","/Users/sellers/.agents/skills/synced/f39d0c09-f607-4b9c-bde5-dbea41e3781a_816383df-c749-4c89-9d32-137316881240/regengine-service-runner/SKILL.md","frontend/package.json","frontend/playwright.config.ts","frontend/next.config.ts","frontend/src/app/page.tsx","frontend/src/app/layout.tsx"]; [print("FILE",p,"\n",Path(p).read_text()) for p in files if Path(p).is_file()]; subprocess.run(["rg","--files","frontend/src/app","frontend/e2e","docs/qa/2026-10-02/scripts","-g","!*lock*","-g","!**/.env*"]); print("env_file_names",[p.name for p in Path("frontend").glob(".env*")]); print("nextdocs",list(Path("frontend/node_modules/next/dist/docs").glob("**/*getting*"))[:15])'`; cwd `.`; exit 0, 0.08s. [Output](artifacts/ux/20261003T003706.795138Z-local-runner-and-routes.txt).

- **2026-10-03T00:37:17.191184+00:00** `guidance` — `python3 -c 'from pathlib import Path; files=["/Users/sellers/.codex/skills/playwright/SKILL.md","/Users/sellers/.agents/skills/synced/f39d0c09-f607-4b9c-bde5-dbea41e3781a_816383df-c749-4c89-9d32-137316881240/regengine-service-runner/SKILL.md","docs/qa/2026-10-02/scripts/node-isolation.cjs","frontend/package.json","frontend/next.config.ts","frontend/playwright.config.ts","frontend/node_modules/next/dist/docs/01-app/01-getting-started/01-installation.mdx"]; [print("FILE",p,"\n",Path(p).read_text()) for p in files if Path(p).is_file()]'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T003717.191184Z-guidance.txt).

- **2026-10-03T00:37:20.959076+00:00** `browser-guidance` — `cat /Users/sellers/.codex/skills/playwright/SKILL.md`; cwd `.`; exit 0, 0.00s. [Output](artifacts/ux/20261003T003720.959076Z-browser-guidance.txt).

- **2026-10-03T00:37:29.722169+00:00** `route-map` — `python3 -c 'from pathlib import Path; import subprocess; subprocess.run(["rg","--files","frontend","-g","*next.config*","-g","!node_modules/**","-g","**/AGENTS.md"]); subprocess.run(["rg","--files","frontend/src/app","frontend/tests/e2e","-g","!**/.env*","-g","**/page.tsx","-g","*.spec.ts"]); [print("FILE",p,"\n",Path(p).read_text()) for p in ["frontend/next.config.mjs","frontend/src/middleware.ts","frontend/src/proxy.ts"] if Path(p).is_file()]'`; cwd `.`; exit 0, 0.06s. [Output](artifacts/ux/20261003T003729.722169Z-route-map.txt).

- **2026-10-03T00:37:35.618614+00:00** `config-and-core-routes` — `python3 -c 'from pathlib import Path; import subprocess; print(Path("frontend/next.config.js").read_text()[:15000]); print("ROUTES",[str(p.relative_to(Path("frontend/src/app"))) for p in Path("frontend/src/app").rglob("page.tsx")][:180]); print("DOCS",[str(p) for p in Path("frontend/node_modules/next/dist/docs/01-app/01-getting-started").iterdir()][:8]); print("TEST FILES",[p.name for p in Path("frontend/tests/e2e").glob("*.spec.ts")])'`; cwd `.`; exit 0, 0.04s. [Output](artifacts/ux/20261003T003735.618614Z-config-and-core-routes.txt).

- **2026-10-03T00:37:41.931545+00:00** `prepare-isolated-mirror` — `python3 -c 'from pathlib import Path; import shutil,tempfile; root=Path.cwd(); tmp=Path(tempfile.mkdtemp(prefix="regengine-qa-ux-",dir="/private/tmp")); app=tmp/"frontend"; shutil.copytree(root/"frontend",app,ignore=lambda base,names:[n for n in names if n in {"node_modules",".next","coverage","test-results","playwright-report",".git"} or n.startswith(".env") or n in {".npmrc",".netrc","credentials"}]); (app/"node_modules").symlink_to(root/"frontend/node_modules",target_is_directory=True); (root/"docs/qa/2026-10-02/artifacts/ux/mirror-path.txt").write_text(str(tmp)); print("QA mirror",tmp); print((root/"frontend/node_modules/next/dist/docs/01-app/01-getting-started/01-installation.md").read_text()[:6500])'`; cwd `.`; exit 0, 0.19s. [Output](artifacts/ux/20261003T003741.931545Z-prepare-isolated-mirror.txt).

- **2026-10-03T00:37:53.511139+00:00** `browsers-and-axe-setup` — `python3 -c 'from pathlib import Path; import subprocess,os; temp=Path("/private/tmp/regengine-qa-ux-u2059hm8"); subprocess.run(["npm","install","--prefix",str(temp/"qa-tools"),"--ignore-scripts","--no-audit","--no-fund","axe-core"],check=True); subprocess.run(["node","frontend/node_modules/playwright/cli.js","install","chromium","firefox","webkit"],env=dict(os.environ,PLAYWRIGHT_BROWSERS_PATH=str(temp/"browsers")),check=True)'`; cwd `.`; exit 1, 0.45s. [Output](artifacts/ux/20261003T003753.511139Z-browsers-and-axe-setup.txt).

- **2026-10-03T00:38:08.017325+00:00** `journey-source` — `python3 -c 'from pathlib import Path; files=["frontend/src/app/verify/page.tsx","frontend/src/app/login/page.tsx","frontend/src/app/demo/page.tsx","frontend/src/app/contact/page.tsx","frontend/src/components/cookie-consent/CookieBanner.tsx"]; [print("FILE",p,"\n",Path(p).read_text()[:7000]) for p in files]'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T003808.017325Z-journey-source.txt).

- **2026-10-03T00:38:13.168920+00:00** `verify-login-structure` — `python3 -c 'from pathlib import Path; import re; files=["frontend/src/app/verify/page.tsx","frontend/src/app/login/page.tsx","frontend/src/components/ui/field.tsx"]; [print("FILE",p,"\n", "\n".join(str(i)+": "+line for i,line in enumerate(Path(p).read_text().splitlines(),1) if re.search(r"fetch|button|input|aria-|<h[123]|useState|iframe|label|return|href|role=|setStatus|code|cloneElement",line))[:10500]) for p in files]'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T003813.168920Z-verify-login-structure.txt).

- **2026-10-03T00:37:58.900557+00:00** `browsers-and-axe-setup-retry` — `python3 -c 'from pathlib import Path; import subprocess,os; temp=Path("/private/tmp/regengine-qa-ux-u2059hm8"); subprocess.run(["npm","install","--prefix",str(temp/"qa-tools"),"--cache",str(temp/"npm-cache"),"--ignore-scripts","--no-audit","--no-fund","axe-core"],check=True); subprocess.run(["node","frontend/node_modules/playwright/cli.js","install","chromium","firefox","webkit"],env=dict(os.environ,PLAYWRIGHT_BROWSERS_PATH=str(temp/"browsers")),check=True)'`; cwd `.`; exit 0, 20.27s. [Output](artifacts/ux/20261003T003758.900557Z-browsers-and-axe-setup-retry.txt).

- **2026-10-03T00:38:19.229011+00:00** `server-preflight` — `python3 -c 'import urllib.request; r=urllib.request.urlopen("http://127.0.0.1:3102",timeout=50); print("status",r.status); print("headers", dict(r.headers)); print("bytes",len(r.read()))'`; cwd `.`; exit 1, 6.85s. [Output](artifacts/ux/20261003T003819.229011Z-server-preflight.txt).

- **2026-10-03T00:39:11.319085+00:00** `restart-guarded-server` — `python3 -c 'import subprocess,os,signal; rows=subprocess.check_output(["ps","-axo","pid=,command="],text=True).splitlines(); ids=[int(row.strip().split(None,1)[0]) for row in rows if row.strip().split(None,1)[1].startswith("node frontend/node_modules/next/dist/bin/next dev /private/tmp/regengine-qa-ux-u2059hm8/frontend")]; print("stopping owned server ids",ids); [os.kill(pid,signal.SIGTERM) for pid in ids]'`; cwd `.`; exit 1, 0.04s. [Output](artifacts/ux/20261003T003911.319085Z-restart-guarded-server.txt).

- **2026-10-03T00:39:22.783060+00:00** `owned-listener-id` — `lsof -n -P -iTCP:3102 -sTCP:LISTEN`; cwd `.`; exit 0, 0.09s. [Output](artifacts/ux/20261003T003922.783060Z-owned-listener-id.txt).

- **2026-10-03T00:39:26.419777+00:00** `stop-owned-listener` — `python3 -c 'import os,signal; os.kill(23587,signal.SIGTERM); print("Sent SIGTERM to observed port-3102 QA listener 23587")'`; cwd `.`; exit 1, 0.03s. [Output](artifacts/ux/20261003T003926.419777Z-stop-owned-listener.txt).

- **2026-10-03T00:39:39.686220+00:00** `reload-qa-mirror-server` — `python3 -c 'from pathlib import Path; import os; p=Path("/private/tmp/regengine-qa-ux-u2059hm8/frontend/next.config.js"); os.utime(p,None); print("Touched only QA mirror next.config.js to trigger guarded server restart; source content unchanged")'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T003939.686220Z-reload-qa-mirror-server.txt).

- **2026-10-03T00:39:50.386865+00:00** `reload-check` — `python3 -c 'import subprocess,urllib.request,urllib.error; subprocess.run(["lsof","-n","-P","-iTCP:3102","-sTCP:LISTEN"]); request=urllib.request.Request("http://127.0.0.1:3102"); opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));
try:
 r=opener.open(request,timeout=15); print("status",r.status); print(r.read(600).decode())
except urllib.error.HTTPError as e:
 print("status",e.code,"body",e.read(600).decode())'`; cwd `.`; exit 0, 0.42s. [Output](artifacts/ux/20261003T003950.386865Z-reload-check.txt).

- **2026-10-03T00:39:57.463887+00:00** `reload-guard-content-marker` — `python3 -c 'from pathlib import Path; p=Path("/private/tmp/regengine-qa-ux-u2059hm8/frontend/next.config.js"); p.write_text(p.read_text()+"\n// QA mirror only: restart process after isolation guard hardening.\n"); print("Added inert restart marker to disposable mirror config only")'`; cwd `.`; exit 0, 0.05s. [Output](artifacts/ux/20261003T003957.463887Z-reload-guard-content-marker.txt).

- **2026-10-03T00:40:04.438806+00:00** `local-route-diagnostic` — `python3 -c 'import subprocess,urllib.request,urllib.error,re; subprocess.run(["lsof","-n","-P","-iTCP:3102","-sTCP:LISTEN"]); opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));
for route in ["/","/login","/verify"]:
 try:
  r=opener.open("http://127.0.0.1:3102"+route,timeout=30); data=r.read().decode(); status=r.status
 except urllib.error.HTTPError as e:
  data=e.read().decode(); status=e.code
 print(route,status,re.findall(r"<h[12][^>]*>(.*?)</h[12]>",data)[:8])'`; cwd `.`; exit 0, 0.22s. [Output](artifacts/ux/20261003T004004.438806Z-local-route-diagnostic.txt).

- **2026-10-03T00:40:16.906152+00:00** `mirror-route-manifest` — `python3 -c 'from pathlib import Path; import json; p=Path("/private/tmp/regengine-qa-ux-u2059hm8/frontend"); print("app candidates",[(str(x),x.is_dir()) for x in [p/"app",p/"src/app",p/"src/app/page.tsx"]]); print("page file bytes",(p/"src/app/page.tsx").stat().st_size); print("manifest",(p/".next/server/app-paths-manifest.json").read_text()[:2000]); print("package scripts",json.loads((p/"package.json").read_text())["scripts"])'`; cwd `.`; exit 1, 0.04s. [Output](artifacts/ux/20261003T004016.906152Z-mirror-route-manifest.txt).

- **2026-10-03T00:40:42.306831+00:00** `guarded-server-v2-preflight` — `python3 -c 'from pathlib import Path; import urllib.request,urllib.error; print(Path("docs/qa/2026-10-02/artifacts/ux/guarded-server-metadata.txt").read_text()); print(Path("docs/qa/2026-10-02/artifacts/ux/guarded-server-output.txt").read_text()[-5000:]); opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));
try:
 r=opener.open("http://127.0.0.1:3104",timeout=40); print("status",r.status,"bytes",len(r.read()))
except urllib.error.HTTPError as e:
 print("status",e.code,"bytes",len(e.read()))'`; cwd `.`; exit 1, 0.12s. [Output](artifacts/ux/20261003T004042.306831Z-guarded-server-v2-preflight.txt).

- **2026-10-03T00:40:53.619301+00:00** `stop-restarting-dev-server` — `python3 -c 'from pathlib import Path; Path("/private/tmp/regengine-qa-ux-u2059hm8/stop-server").touch(); print("Requested cooperative stop of owned v2 server")'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T004053.619301Z-stop-restarting-dev-server.txt).

- **2026-10-03T00:40:36.067108+00:00** `guarded-server-v2` — `python3 docs/qa/2026-10-02/scripts/ux-server.py`; cwd `.`; exit 0, 17.92s. [Output](artifacts/ux/20261003T004036.067108Z-guarded-server-v2.txt).

- **2026-10-03T00:41:23.566237+00:00** `built-server-preflight` — `python3 -c 'from pathlib import Path; import urllib.request,urllib.error; print(Path("docs/qa/2026-10-02/artifacts/ux/built-server-metadata.txt").read_text()); print(Path("docs/qa/2026-10-02/artifacts/ux/built-server-output.txt").read_text()[-3000:]); opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); r=opener.open("http://127.0.0.1:3104",timeout=30); print("status",r.status,"bytes",len(r.read()))'`; cwd `.`; exit 1, 0.09s. [Output](artifacts/ux/20261003T004123.566237Z-built-server-preflight.txt).

- **2026-10-03T00:41:30.248988+00:00** `startup-assertion-requirements` — `rg -n 'startup|CSRF_SECRET|JWT_SIGNING|production|assert' frontend/src/instrumentation.ts frontend/src/lib/startup-assertions.ts`; cwd `.`; exit 2, 0.01s. [Output](artifacts/ux/20261003T004130.248988Z-startup-assertion-requirements.txt).

- **2026-10-03T00:41:30.337915+00:00** `stop-unconfigured-built-server` — `python3 -c 'from pathlib import Path; Path("/private/tmp/regengine-qa-ux-u2059hm8/stop-built-server").touch(); print("Requested cooperative stop; missing synthetic production-mode CSRF runtime value")'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T004130.337915Z-stop-unconfigured-built-server.txt).

- **2026-10-03T00:41:17.828789+00:00** `guarded-built-server` — `python3 docs/qa/2026-10-02/scripts/ux-server.py`; cwd `.`; exit 0, 12.57s. [Output](artifacts/ux/20261003T004117.828789Z-guarded-built-server.txt).

- **2026-10-03T00:41:43.828393+00:00** `ready-server-preflight` — `python3 -c 'from pathlib import Path; import urllib.request; print(Path("docs/qa/2026-10-02/artifacts/ux/ready-server-metadata.txt").read_text()); print(Path("docs/qa/2026-10-02/artifacts/ux/ready-server-output.txt").read_text()[-2000:]); opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); r=opener.open("http://127.0.0.1:3104",timeout=30); print("status",r.status,"bytes",len(r.read()))'`; cwd `.`; exit 0, 0.25s. [Output](artifacts/ux/20261003T004143.828393Z-ready-server-preflight.txt).

- **2026-10-03T00:41:50.831989+00:00** `cross-browser-smoke` — `env QA_MIRROR=/private/tmp/regengine-qa-ux-u2059hm8 PLAYWRIGHT_BROWSERS_PATH=/private/tmp/regengine-qa-ux-u2059hm8/browsers node docs/qa/2026-10-02/scripts/ux-browser-pass.cjs smoke`; cwd `.`; exit 0, 9.53s. [Output](artifacts/ux/20261003T004150.831989Z-cross-browser-smoke.txt).

- **2026-10-03T00:42:05.747355+00:00** `login-verify-control-source` — `python3 -c 'from pathlib import Path; print(Path("frontend/src/app/login/page.tsx").read_text()); p=Path("frontend/src/app/verify/page.tsx"); print("VERIFY", "\n".join(f"{i}: {line}" for i,line in enumerate(p.read_text().splitlines(),1) if 145<=i<=280)); print("LOGIN CANDIDATES",[str(p) for p in Path("frontend/src").rglob("*login*")])'`; cwd `.`; exit 0, 0.04s. [Output](artifacts/ux/20261003T004205.747355Z-login-verify-control-source.txt).

- **2026-10-03T00:46:19.808124+00:00** `chrome-axe-initial-results` — `python3 -c 'from pathlib import Path; import json; p=Path("docs/qa/2026-10-02/artifacts/ux"); files=list(p.glob("chrome-axe*.json")); print("reports",[x.name for x in files]);
for f in files:
 d=json.loads(f.read_text()); print(f.name,"width",d["width"],"document",d["documentWidth"],"axe",[(x["id"],x["impact"],len(x["nodes"])) for x in d["axe"]["violations"]],"camera",d.get("cameraAllowed"))'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T004619.808124Z-chrome-axe-initial-results.txt).

- **2026-10-03T00:46:24.441943+00:00** `axe-first-node-details` — `python3 -c 'import json;from pathlib import Path;d=json.loads(Path("docs/qa/2026-10-02/artifacts/ux/chrome-axe_-1728-1.json").read_text());print(json.dumps(d["axe"]["violations"],indent=2)[:5000])'`; cwd `.`; exit 0, 0.16s. [Output](artifacts/ux/20261003T004624.441943Z-axe-first-node-details.txt).

- **2026-10-03T00:48:04.045958+00:00** `stop-proxy-for-mobile-harness` — `python3 -c 'from pathlib import Path; Path("/private/tmp/regengine-qa-ux-u2059hm8/stop-proxy").touch(); print("Requested cooperative QA proxy stop; adding real app iframe responsive harness")'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T004804.045958Z-stop-proxy-for-mobile-harness.txt).

- **2026-10-03T00:43:54.833024+00:00** `managed-chrome-local-proxy` — `python3 docs/qa/2026-10-02/scripts/ux-local-proxy.py`; cwd `.`; exit 0, 249.45s. [Output](artifacts/ux/20261003T004354.833024Z-managed-chrome-local-proxy.txt).

- **2026-10-03T00:48:37.146107+00:00** `mobile-menu-and-axe-review` — `python3 -c 'from pathlib import Path; import json,re; p=Path("frontend/src/components/layout/marketing-header.tsx"); lines=p.read_text().splitlines(); print("\n".join(f"{i}: {l}" for i,l in enumerate(lines,1) if re.search("Escape|keydown|mobileMenu|aria-modal|role=|dialog|onKeyDown|tabIndex|setIsOpen|setMobile|focus",l))); 
for f in Path("docs/qa/2026-10-02/artifacts/ux").glob("chrome-axe*.json"):
 d=json.loads(f.read_text()); print(f.name,"size",d["width"],d["documentWidth"],[(v["id"],len(v["nodes"])) for v in d["axe"]["violations"]])'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T004837.146107Z-mobile-menu-and-axe-review.txt).

- **2026-10-03T00:48:41.156858+00:00** `menu-keyboard-source` — `rg -n 'function Mobile|Escape|keydown|aria-modal|role="dialog"|focus\(' frontend/src/components/layout/marketing-header.tsx frontend/src/components/layout/marketing-nav.ts`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T004841.156858Z-menu-keyboard-source.txt).

- **2026-10-03T00:48:45.116945+00:00** `mobile-drawer-source` — `python3 -c 'from pathlib import Path; import subprocess; print("\n".join(Path("frontend/src/components/layout/marketing-header.tsx").read_text().splitlines()[:20])); subprocess.run(["rg","-n","export.*MobileNav|function MobileNav|function MobileHamburger|aria-modal","frontend/src/components/layout"])'`; cwd `.`; exit 0, 0.04s. [Output](artifacts/ux/20261003T004845.116945Z-mobile-drawer-source.txt).

- **2026-10-03T00:48:50.605460+00:00** `mobile-dialog-source-lines` — `python3 -c 'from pathlib import Path; print("\n".join(f"{i}: {l}" for i,l in enumerate(Path("frontend/src/components/layout/header/MobileMenu.tsx").read_text().splitlines(),1)))'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/ux/20261003T004850.605460Z-mobile-dialog-source-lines.txt).

- **2026-10-03T00:50:56.866742+00:00** `demo-status-source` — `python3 -c 'from pathlib import Path; import subprocess; subprocess.run(["rg","-n","function DemoBanner|Backend unavailable|DemoBanner visible","frontend/src"]); print("CURRENT AXE"); import json;
for f in Path("docs/qa/2026-10-02/artifacts/ux").glob("chrome-axe*.json"):
 d=json.loads(f.read_text()); v=[(x["id"],len(x["nodes"])) for x in d["axe"]["violations"] if not all("aiFabShadowRoot" in str(n["target"]) for n in x["nodes"])]; print(f.name,"width",d["width"],"doc",d["documentWidth"],"product violations",v)'`; cwd `.`; exit 0, 0.07s. [Output](artifacts/ux/20261003T005056.866742Z-demo-status-source.txt).

- **2026-10-03T00:51:02.929390+00:00** `narrow-verifier-axe-evidence` — `python3 -c 'import json;from pathlib import Path;d=json.loads(Path("docs/qa/2026-10-02/artifacts/ux/chrome-axe_verify-320-004936758162.json").read_text()); print(json.dumps([{k:v for k,v in x.items() if k in {"id","impact","tags","nodes"}} for x in d["axe"]["violations"]],indent=2)[:9500])'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/ux/20261003T005102.929390Z-narrow-verifier-axe-evidence.txt).

- **2026-10-03T00:52:34.958253+00:00** `final-evidence-summary` — `python3 -c 'from pathlib import Path; import json,re; out=Path("docs/qa/2026-10-02/artifacts/ux"); rows=[]
for f in sorted(out.glob("chrome-axe*.json")):
 d=json.loads(f.read_text()); violations=[{"id":v["id"],"impact":v["impact"],"nodes":[n for n in v["nodes"] if "aiFabShadowRoot" not in str(n["target"])]} for v in d["axe"]["violations"]]; violations=[v for v in violations if v["nodes"]]; rows.append({"artifact":f.name,"path":d["url"],"width":d["width"],"documentWidth":d["documentWidth"],"violations":[{"id":v["id"],"nodes":len(v["nodes"])} for v in violations],"passes":len(d["axe"]["passes"]),"incomplete":len(d["axe"]["incomplete"]),"lcp":d.get("lcp"),"cls":d.get("cls"),"navigation":d["navigation"],"errors":d["errors"]})
(out/"axe-summary.json").write_text(json.dumps(rows,indent=2)); print(json.dumps(rows,indent=2)); print("SCREENSHOTS",[f.name for f in out.glob("*.jpg")]);
for file in ["frontend/src/app/verify/page.tsx","frontend/src/components/ui/table.tsx","frontend/src/app/tools/ftl-checker/page.tsx","frontend/src/components/control-plane/demo-banner.tsx"]:
 p=Path(file); print("SOURCE",file); print("\n".join(f"{i}: {l}" for i,l in enumerate(p.read_text().splitlines(),1) if re.search("overflow-auto|overflow-x|filtered|\.map\\(|No.*result|Backend unavailable|tabIndex",l)))'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T005234.958253Z-final-evidence-summary.txt).

- **2026-10-03T00:52:58.767183+00:00** `empty-search-source` — `rg -n 'filteredCategories|filteredProducts|No.*result|searchQuery|setSearch|categories.filter' frontend/src/app/tools/ftl-checker frontend/src/components/tools`; cwd `.`; exit 0, 0.01s. [Output](artifacts/ux/20261003T005258.767183Z-empty-search-source.txt).

- **2026-10-03T00:53:08.615187+00:00** `empty-search-source-lines` — `python3 -c 'from pathlib import Path; p=Path("frontend/src/app/tools/ftl-checker/components/FTLCheckerClient.tsx"); print("\n".join(f"{i}: {l}" for i,l in enumerate(p.read_text().splitlines(),1) if 760<=i<=865))'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/ux/20261003T005308.615187Z-empty-search-source-lines.txt).

- **2026-10-03T00:53:44.621513+00:00** `redirect-guard-unit-probe` — `python3 -c 'from pathlib import Path; import urllib.request,urllib.error; source=Path("docs/qa/2026-10-02/scripts/ux-local-proxy.py").read_text(); namespace={"__file__":str(Path("docs/qa/2026-10-02/scripts/ux-local-proxy.py").resolve())}; exec(source.split("server=ThreadingHTTPServer",1)[0],namespace); handler=namespace["LocalRedirectsOnly"]();
for target in ["https://example.invalid","http://127.0.0.1:3103","http://localhost:3104"]:
 try: handler.redirect_request(urllib.request.Request("http://127.0.0.1:3104/"),None,302,"Found",{},target); raise AssertionError("unexpected redirect allowed")
 except urllib.error.HTTPError as e: assert e.code==502; print("blocked",target)
r=handler.redirect_request(urllib.request.Request("http://127.0.0.1:3104/"),None,302,"Found",{},"http://127.0.0.1:3104/login"); assert r.full_url=="http://127.0.0.1:3104/login"; print("PASS local redirect allowed;3 off-origin redirects blocked; no requests executed")'`; cwd `.`; exit 0, 0.07s. [Output](artifacts/ux/20261003T005344.621513Z-redirect-guard-unit-probe.txt).

- **2026-10-03T00:54:01.143186+00:00** `cooperative-cleanup` — `python3 -c 'from pathlib import Path; base=Path("/private/tmp/regengine-qa-ux-u2059hm8"); [(base/name).touch() for name in ["stop-proxy-v2","stop-ready-server"]]; print("Requested cooperative stop of QA proxy3105 and guarded built-server3104; browser tabs already closed")'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T005401.143186Z-cooperative-cleanup.txt).

- **2026-10-03T00:41:42.694112+00:00** `guarded-ready-server` — `python3 docs/qa/2026-10-02/scripts/ux-server.py`; cwd `.`; exit 0, 738.57s. [Output](artifacts/ux/20261003T004142.694112Z-guarded-ready-server.txt).

- **2026-10-03T00:48:04.341022+00:00** `managed-chrome-proxy-v2` — `python3 docs/qa/2026-10-02/scripts/ux-local-proxy.py`; cwd `.`; exit 0, 357.17s. [Output](artifacts/ux/20261003T004804.341022Z-managed-chrome-proxy-v2.txt).

- **2026-10-03T00:54:06.952529+00:00** `listener-cleanup-check` — `python3 -c 'import subprocess; from pathlib import Path; import datetime; print("UTC",datetime.datetime.now(datetime.timezone.utc).isoformat());
for port in [3102,3104,3105]:
 r=subprocess.run(["lsof","-n","-P",f"-iTCP:{port}","-sTCP:LISTEN"],capture_output=True,text=True); print("port",port,"exit",r.returncode,"output",r.stdout.strip())'`; cwd `.`; exit 0, 0.24s. [Output](artifacts/ux/20261003T005406.952529Z-listener-cleanup-check.txt).

- **2026-10-03T00:56:32.167121+00:00** `final-log-inspection` — `python3 -c 'from pathlib import Path; p=Path("docs/qa/2026-10-02/UX-SESSION-LOG.md"); print(p.read_text()[-14000:]); print("REPORT_EXISTS", Path("docs/qa/2026-10-02/UX-REPORT.md").exists()); print("KEYBOARD_EXISTS", Path("docs/qa/2026-10-02/artifacts/ux/manual-keyboard-evidence.json").exists())'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/ux/20261003T005632.167121Z-final-log-inspection.txt).

- **2026-10-03T00:56:41.840491+00:00** `orphan-cooperative-config-exit` — `python3 -c 'from pathlib import Path; import time,subprocess; p=Path("/private/tmp/regengine-qa-ux-u2059hm8/frontend/next.config.js"); assert p.is_file(); p.write_text(p.read_text()+"\n// QA disposable mirror only: cooperative shutdown after completed sweep.\nprocess.exit(0);\n"); print("Appended cooperative exit to disposable mirror only"); time.sleep(3); r=subprocess.run(["lsof","-n","-P","-iTCP:3102","-sTCP:LISTEN"],capture_output=True,text=True); print("Listener check exit",r.returncode); print(r.stdout)'`; cwd `.`; exit 0, 3.10s. [Output](artifacts/ux/20261003T005641.840491Z-orphan-cooperative-config-exit.txt).

- **2026-10-03T00:56:48.390968+00:00** `final-report-review` — `python3 -c 'from pathlib import Path; print(Path("docs/qa/2026-10-02/UX-REPORT.md").read_text()); print(Path("docs/qa/2026-10-02/artifacts/ux/manual-keyboard-evidence.json").read_text())'`; cwd `.`; exit 0, 0.02s. [Output](artifacts/ux/20261003T005648.390968Z-final-report-review.txt).

- **2026-10-03T00:57:44.722214+00:00** Native browser session completion: exact HTTP timestamps, native action observation windows, failures, screenshot persistence, interrupted original server command and residual cleanup are recorded in [UX-BROWSER-SESSION-LOG.md](UX-BROWSER-SESSION-LOG.md). Report and keyboard evidence were created via QA-only apply_patch edits; no product code changed.

- **2026-10-03T00:57:44.699870+00:00** `append-native-session-index` — `python3 -c 'from pathlib import Path; from datetime import datetime,timezone; p=Path("docs/qa/2026-10-02/UX-SESSION-LOG.md"); stamp=datetime.now(timezone.utc).isoformat(); p.open("a").write("\n- **"+stamp+"** Native browser session completion: exact HTTP timestamps, native action observation windows, failures, screenshot persistence, interrupted original server command and residual cleanup are recorded in [UX-BROWSER-SESSION-LOG.md](UX-BROWSER-SESSION-LOG.md). Report and keyboard evidence were created via QA-only apply_patch edits; no product code changed.\n"); print("Native browser chronology linked from primary UX log")'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T005744.699870Z-append-native-session-index.txt).

- **2026-10-03T00:57:44.805622+00:00** `final-ux-link-check` — `python3 -c 'from pathlib import Path; import re,json; base=Path("docs/qa/2026-10-02"); missing=[]; count=0
for name in ["UX-REPORT.md","UX-BROWSER-SESSION-LOG.md"]:
 for link in re.findall(r"\]\(([^)]+)\)",(base/name).read_text()):
  if not link.startswith(("http:","https:")):
   count+=1
   if not (base/link).exists(): missing.append((name,link))
json.loads((base/"artifacts/ux/manual-keyboard-evidence.json").read_text()); print("Local links checked",count,"missing",missing); assert not missing; print("PASS manual evidence JSON parses")'`; cwd `.`; exit 0, 0.03s. [Output](artifacts/ux/20261003T005744.805622Z-final-ux-link-check.txt).

- **2026-10-03T00:57:44.805636+00:00** `final-qa-script-syntax` — `python3 -c 'import ast,subprocess; from pathlib import Path; base=Path("docs/qa/2026-10-02/scripts"); [ast.parse((base/n).read_text(),filename=n) for n in ["ux-server.py","ux-local-proxy.py"]]; subprocess.run(["node","--check",str(base/"ux-browser-pass.cjs")],check=True); print("PASS: two Python AST parses and Node browser script syntax")'`; cwd `.`; exit 0, 0.06s. [Output](artifacts/ux/20261003T005744.805636Z-final-qa-script-syntax.txt).
