# Pre-Public Checklist

**This repository is private.** This checklist is the gate that must be cleared
*before* its visibility is changed. It exists because `README.md` previously
stated the repository was already public (#2811) — an inaccurate claim that
someone could reasonably have acted on.

Nothing here blocks day-to-day work. It blocks exactly one action: flipping the
repository to public.

---

## 1. Confidential material is still tracked

The paths below are business and fundraising material, outside the scope
`REPO_PURPOSE.md` defines for this repository. They serve no build, test, or
deploy purpose. **They are listed by path only; do not paste their contents into
issues, pull requests, or commit messages** — those are repository artifacts too.

<!-- The block below is parsed by tests/security/test_repo_visibility_claims_2811.py.
     Keep one path per line. Add a path here when confidential material is added
     to the tree; remove one only when it is genuinely untracked. -->

```confidential-paths
RegEngine_Investor_Outreach_Memo.docx
RegEngine_Investor_Outreach_Memo_Inflow_Workbench_Update.docx
docs/archive/REGENGINE_EVALUATION_2026-03-27.md
docs/archive/RegEngine_PRD_Investor_Sprint.docx
docs/product/DATA_ROOM_INDEX.md
docs/product/HONEST_VALUATION_UPDATE_2026-04-30.md
docs/product/Honest_Valuation_Update_2026-04-30.pdf
launch_orchestrator/investors/DATA_ROOM_STRUCTURE.md
launch_orchestrator/investors/FUNDRAISING_CHECKLIST.md
launch_orchestrator/investors/INVESTOR_FAQ.md
launch_orchestrator/investors/INVESTOR_OUTREACH_SEQUENCE.md
launch_orchestrator/investors/investor_feedback_action_plan.md
launch_orchestrator/investors/investor_memo.md
launch_orchestrator/sales/fsma_investor_brief.md
production_bundle/documentation/Investor_Whitepaper_v1.0.md
```

`docs/whitepapers/` is **not** on this list: it holds publishing tooling
(`export_pdf.sh`, `pdf-template.yaml`, a formatting guide), not business content.

## 2. Removing them from `HEAD` is not enough

`git rm --cached <path>` removes a file from the index and from future commits.
**Every prior revision remains readable**, so on a public repository the material
is still fully retrievable by anyone who clones and checks out an older commit.

Making this repository public therefore requires a **history rewrite** — the
paths purged from every reachable commit, not merely deleted at `HEAD`.

That is a rewrite affecting all clones and all open branches. At the time of
writing there are dozens of open pull-request branches; each would need to be
rebased onto the rewritten history or closed. **Plan it deliberately; do not do
it reactively at flip time.**

## 3. The order that matters

1. **Decide the intended visibility.** If the repository stays private,
   the only outstanding work is keeping `README.md` accurate — which is done.
2. If it is to become public, **first** relocate the paths in §1 to the document
   store outside version control, and add matching `.gitignore` entries. Ignore
   rules do **not** retroactively untrack files already in the index.
3. **Then** purge the paths from history (§2), and re-audit the tree from
   scratch — this checklist is a snapshot, not a guarantee.
4. Only then change the visibility setting.

## 4. Related

- `REPO_PURPOSE.md` — the scope these files fall outside of.
- `SECURITY.md` — reporting and disclosure posture.
- The public proof surface (`/proof`, `/verify`) already provides
  transparency and audit **without** requiring source visibility. It is the
  reason the README's public-repository claim sounded plausible.
