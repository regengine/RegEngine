# Antigravity / Agent Skills compatibility layer

This folder is for editor-facing rules, workflows, and skills.

- `.agent/` remains the legacy swarm-script layer used by repo-local Python tooling.
- `.agents/` is the compatibility layer for tools that expect rules, workflows, and skills in the Agent Skills / Antigravity style layout.

Do not delete `.agent/` unless you also migrate the repo-local swarm scripts.
