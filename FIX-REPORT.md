# FIX-REPORT: About page copy

Copy-only change in `frontend/src/app/about/page.tsx`. Two sentences were reworded. The published price was not changed.

## Before and after

1. Verification sentence (principle "Verifiable, not just claimed")

Before:
`Customers can independently verify export-bundle integrity using our published verify_chain.py script.`

After:
`You can independently verify export-bundle integrity using our published verify_chain.py script.`

The rest of that sentence is unchanged: "Compliance records are hash-linked once ingested, so any later change is detectable."

2. Faster iteration card

Before:
`Design-partner feedback is scoped to`

After:
`Early tester feedback is scoped to`

The rendered sentence now reads: "No committee approvals. Early tester feedback is scoped to ship within days, not quarters."

The following line was not changed: "Regulatory updates deploy without waiting for quarterly release trains."

Price left as it was:
`RegEngine starts at $425/mo (billed annually).`

## Diff

`git diff --stat` (tracked files only):

```
 frontend/src/app/about/page.tsx | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)
```

Two hunks from `git diff -- frontend/src/app/about/page.tsx`:

```
@@ -69,7 +69,7 @@ const PRINCIPLES = [
     Icon: Shield,
     title: "Verifiable, not just claimed",
     description:
-      "Compliance records are hash-linked once ingested, so any later change is detectable. Customers can independently verify export-bundle integrity using our published verify_chain.py script.",
+      "Compliance records are hash-linked once ingested, so any later change is detectable. You can independently verify export-bundle integrity using our published verify_chain.py script.",
   },
   {
     Icon: Lightbulb,
@@ -206,7 +206,7 @@ export default function AboutPage() {
                 Faster iteration
               </p>
               <p className="mt-1 text-ui text-re-text-secondary">
-                No committee approvals. Design-partner feedback is scoped to
+                No committee approvals. Early tester feedback is scoped to
                 ship within days, not quarters. Regulatory updates deploy
                 without waiting for quarterly release trains.
               </p>
```

Untracked test file, not included in `git diff --stat`:
`frontend/src/__tests__/pages/about-copy.test.tsx`

`frontend/next-env.d.ts` was rewritten by `next build` (dev type paths became production type paths). That file was put back to the committed text. It is not part of this change.

## Build, typecheck, and lint

Install, from `frontend/`, lockfile `package-lock.json`:

`~/metacode/fleet/heavy npm ci`

Result: exit 0. Added 793 packages in 27s. npm also printed 10 high severity audit findings in the existing tree. `npm audit fix` was not run.

Test before the page edit (source assertions only, 2 tests):

`~/metacode/fleet/heavy ./node_modules/.bin/vitest run src/__tests__/pages/about-copy.test.tsx`

Result: exit 1.

```
Test Files  1 failed (1)
     Tests  2 failed (2)
```

Both failed because the file still had "Customers can independently verify..." and "Design-partner feedback is scoped to", and did not contain the new phrases.

Test after the page edit, then again after a render assertion was added:

`~/metacode/fleet/heavy ./node_modules/.bin/vitest run src/__tests__/pages/about-copy.test.tsx`

Result: exit 0. Final run: 1 file passed, 3 tests passed.

Lint on the page and the test:

`~/metacode/fleet/heavy ./node_modules/.bin/eslint src/app/about/page.tsx src/__tests__/pages/about-copy.test.tsx`

Result: exit 0, no findings.

Typecheck of the final tree:

`~/metacode/fleet/heavy ./node_modules/.bin/tsc --noEmit --pretty false --incremental false`

Result: exit 0. An earlier `tsc` run, before the render assertion existed, also exited 0.

Production build, from `frontend/`:

`~/metacode/fleet/heavy npm run build`

Result: exit 0. Next.js 16.3.6 compiled successfully in 13.4s, finished TypeScript in 9.8s, and generated 172 static pages. `/about` is in the route list. Warnings were the usual ones: no build cache, anonymous telemetry notice, custom Cache-Control header, and Edge Runtime deprecation. No build error.

Ruff was not run. This change is TypeScript only.

Browser: the About page was not opened in a browser. The vitest render asserts the visible joined sentence, and `npm run build` compiled the route.
