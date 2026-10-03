# Resume bootstrap commands

These commands were executed successfully before the existing logger had been read, except the explicitly noted missing skill path. Their exact individual UTC start times were not captured; all precede the first recorded resume command at 2026-10-03T00:35:16.224243Z. This is a reconstruction from the tool invocation history, not a fabricated timestamped transcript. Working directory for each command was the requested RegEngine QA checkout. Subsequent commands use the timestamped logger.

1. Identity, exit 0:

```sh
pwd && git status --short --branch && git worktree list && git remote get-url origin
```

2. Lightweight memory pass, exit 0:

```sh
rg -n 'QA|qa-sweep|tenant isolation|ingestion hardening|symlink' /Users/sellers/.codex/memories/MEMORY.md
```

3. Partial evidence inventory and skill reads, exit 0:

```sh
rg --files docs/qa/2026-10-02 -g '!*.png' -g '!*.jpg' -g '!*.json' -g '!*.html' && cat /Users/sellers/.codex/skills/review-pr/SKILL.md && cat /Users/sellers/.codex/skills/playwright/SKILL.md && cat /Users/sellers/.agents/skills/code-review/SKILL.md
```

4. Read the preserved prior run, exit 0 (tool output truncated; source artifacts preserved):

```sh
cat docs/qa/2026-10-02/META-SESSION-LOG.md docs/qa/2026-10-02/scripts/run_logged.py docs/qa/2026-10-02/artifacts/meta/*.txt
```

5. Instruction discovery and memory details, exit 1 only because the final skill path was incorrect:

```sh
rg --files -g AGENTS.md -g '!node_modules' -g '!vendor' -g '!docs/archive/**'; sed -n '54,87p' /Users/sellers/.codex/memories/MEMORY.md; cat /Users/sellers/.agents/skills/security-best-practices/SKILL.md
```

The security skill was subsequently read at `/Users/sellers/.codex/skills/security-best-practices/SKILL.md` in the logged `scope-map` command. Memory guided test selection only; findings are grounded in current source and local experiments.
