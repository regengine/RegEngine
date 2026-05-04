"""CLI entry point for the legacy autonomous agent swarm.

Usage:
    python -m regengine.swarm status

Legacy execution commands require REGENGINE_ENABLE_LEGACY_SWARM=1.
The supported small-scale helper is:
    python3 scripts/summon_agent.py --list
"""

import argparse
import json
import os
import sys

import structlog

LEGACY_SWARM_ENV = "REGENGINE_ENABLE_LEGACY_SWARM"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _legacy_swarm_enabled() -> bool:
    return os.getenv(LEGACY_SWARM_ENV, "").strip().lower() in _TRUE_VALUES


def _legacy_swarm_notice(command: str) -> str:
    return (
        f"ERROR: regengine.swarm {command} is part of the legacy autonomous swarm runtime.\n"
        "Autonomous swarm execution is disabled by default under the current agent operating model.\n"
        f"Set {LEGACY_SWARM_ENV}=1 only for an explicitly approved legacy run.\n"
        "Supported path: python3 scripts/summon_agent.py --list"
    )


def _require_legacy_swarm_enabled(command: str) -> None:
    if not _legacy_swarm_enabled():
        print(_legacy_swarm_notice(command), file=sys.stderr)
        sys.exit(2)


def configure_logging(verbose: bool = False) -> None:
    """Configure structlog for CLI output."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def cmd_run(args) -> None:
    """Run the agent swarm on a natural language task."""
    _require_legacy_swarm_enabled("run")

    from regengine.swarm.coordinator import AgentSwarm
    from regengine.swarm.llm import LLMClientFactory, MockLLMClient

    print(f"🧬 Agent Swarm — Solving: {args.task}\n")

    if args.dry_run:
        print("🏜️  DRY RUN MODE — using mock LLM\n")
        mock_responses = [
            # Planner response
            json.dumps({
                "steps": [
                    {"id": 1, "action": "Analyze requirements", "files": ["requirements.md"], "details": "Review task", "acceptance_criteria": "Requirements understood"},
                    {"id": 2, "action": "Implement changes", "files": ["app.py"], "details": "Write code", "acceptance_criteria": "Code compiles"},
                ],
                "risks": ["Needs integration testing"],
                "estimated_complexity": "medium",
            }),
            # Coder response
            json.dumps({
                "files": [{"path": "app.py", "action": "modify", "content": "# Implementation placeholder\n", "language": "python"}],
                "summary": "Implemented changes per plan",
                "dependencies_added": [],
            }),
            # Reviewer response
            json.dumps({
                "verdict": "approve",
                "score": 0.85,
                "issues": [],
                "strengths": ["Clean implementation", "Follows patterns"],
                "summary": "Code looks good",
            }),
            # Tester response
            json.dumps({
                "test_files": [{"path": "test_app.py", "content": "def test_example(): pass\n", "test_count": 1}],
                "scenarios_covered": ["happy_path", "edge_case", "error_handling"],
                "coverage_estimate": "85%",
                "summary": "Tests generated",
            }),
        ]
        llm = MockLLMClient(responses=mock_responses)
    else:
        llm = LLMClientFactory.create()
        print(f"🤖 LLM Provider: {llm.model}\n")

    swarm = AgentSwarm(llm_client=llm, max_iterations=args.max_iterations)
    import asyncio
    
    if args.agent:
        print(f"🕵️  Directing task to: {args.agent}\n")
        agent_instance = swarm.agents.get(args.agent)
        if not agent_instance:
            print(f"❌ Error: Agent '{args.agent}' not found. Available: {list(swarm.agents.keys())}")
            sys.exit(1)
        
        # Security audit logic for direct agent call
        if args.agent == "security":
            result_data = asyncio.run(agent_instance.run(args.task))
            print(json.dumps(result_data, indent=2))
            
            # Post to GitHub if in CI and it's a PR
            if os.getenv("GITHUB_ACTIONS") == "true":
                try:
                    from regengine.swarm.github_integration import GitHubClient
                    gh = GitHubClient()
                    
                    # Extract PR number from task or env if possible
                    # Task format usually: "Audit PR #123 ..."
                    import re
                    match = re.search(r"PR #(\d+)", args.task)
                    pr_num = int(match.group(1)) if match else None
                    
                    if pr_num:
                        res = result_data.get("result", {})
                        vulnerabilities = res.get("vulnerabilities", [])
                        verdict = "✅ PASS" if res.get("verdict") == "pass" else "❌ FAIL"
                        
                        comment = f"### 🛡️ Autonomous Security Audit: {verdict}\n\n"
                        comment += f"**Summary:** {res.get('summary', 'Audit complete')}\n"
                        comment += f"**Score:** {res.get('score', 0.0)*100:.1f}%\n\n"
                        
                        if vulnerabilities:
                            comment += "#### ⚠️ Findings:\n"
                            for v in vulnerabilities:
                                comment += f"- **[{v['severity'].upper()}]** {v['issue']} in `{v['file']}`\n"
                                comment += f"  - *Remediation:* {v['remediation']}\n"
                        else:
                            comment += "✨ No critical vulnerabilities identified.\n"
                        
                        gh.comment_on_issue(pr_num, comment)
                        print(f"💬 Security report posted to PR #{pr_num}")
                except Exception as e:
                    print(f"⚠️ Failed to post security report: {e}")
            return

        # Janitor logic for direct agent call
        if args.agent == "janitor":
            from regengine.swarm.github_integration import GitHubClient
            gh = GitHubClient()
            prs = gh.repo.get_pulls(state="open")
            
            print(f"🧹 Janitor scanning {prs.totalCount} open Pull Requests...\n")
            
            for pr in prs:
                print(f"🔍 Evaluating PR #{pr.number}: {pr.title}")
                
                # Gather context for Janitor
                security_comments = [c.body for c in pr.get_issue_comments() if "Security Audit" in c.body]
                test_results = "CI status: " + gh.get_pr_checks_status(pr.number)
                
                context = {
                    "security_scorecard": "\n".join(security_comments) if security_comments else "No security audit found.",
                    "test_results": test_results,
                    "ci_status": gh.get_pr_checks_status(pr.number)
                }
                
                agent_output = asyncio.run(agent_instance.run(f"Evaluate PR #{pr.number}", context))
                res = agent_output.get("result", {})
                decision = res.get("decision", "hold")
                reasoning = res.get("reasoning", "No reasoning.")
                
                print(f"   - Decision: {decision.upper()}")
                print(f"   - Reasoning: {reasoning}")
                
                if decision == "merge":
                    print(f"   🚀 AUTOMATIC MERGE TRIGGERED for PR #{pr.number}...")
                    success = gh.merge_pr(pr.number)
                    if success:
                        print(f"   ✅ PR #{pr.number} merged successfully.")
                    else:
                        print(f"   ❌ Merge failed for PR #{pr.number}.")
            return

        result = asyncio.run(swarm.solve(args.task))
    else:
        result = asyncio.run(swarm.solve(args.task))

    print("\n" + "═" * 60)
    print(f"📊 Result: {result.status}")
    print(f"   Agents: {', '.join(result.agents_used)}")
    print(f"   Iterations: {result.iterations}")
    print(f"   Duration: {result.duration_seconds}s")

    if result.errors:
        print(f"   ❌ Errors: {len(result.errors)}")
        for err in result.errors:
            print(f"      - {err}")

    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(result.to_json())
        print(f"\n💾 Output saved to: {args.output_file}")


def cmd_troubleshoot(args) -> None:
    """Run the CI resilience agent to troubleshoot and heal failures."""
    _require_legacy_swarm_enabled("troubleshoot")

    import asyncio
    from regengine.swarm.coordinator import AgentSwarm

    # Resolve log content: --log-file takes precedence over --logs
    logs: str = ""
    if getattr(args, "log_file", None):
        if args.log_file == "-":
            logs = sys.stdin.read()
        else:
            with open(args.log_file, "r") as fh:
                logs = fh.read()
    elif getattr(args, "logs", None):
        logs = args.logs
    else:
        print("❌ Error: Provide --logs or --log-file")
        sys.exit(1)

    print(f"🧬 CI Resilience Agent — Analyzing {len(logs)} chars of logs...\n")

    swarm = AgentSwarm()
    result = asyncio.run(swarm.troubleshoot(logs))

    print("\n" + "═" * 60)
    print(f"📊 Diagnosis: {result.status}")
    print(f"   Root Cause: {result.plan.get('root_cause') if result.plan else 'Unknown'}")
    print(f"   Remediation: {result.plan.get('immediate_fix') if result.plan else 'None'}")
    print(f"   Agents: {', '.join(result.agents_used)}")
    print(f"   Duration: {result.duration_seconds}s")


def cmd_solve(args) -> None:
    """Solve a GitHub issue using the agent swarm."""
    _require_legacy_swarm_enabled("solve")

    from regengine.swarm.github_integration import GitHubClient
    from regengine.swarm.coordinator import AgentSwarm

    print(f"🧬 Agent Swarm — Solving Issue #{args.issue}\n")

    gh = GitHubClient(repo_name=args.repo)
    issue = gh.get_issue(args.issue)

    print(f"📋 Issue: {issue['title']}")
    print(f"   Labels: {issue['labels']}")
    print(f"   URL: {issue['url']}\n")

    task = f"GitHub Issue #{issue['number']}: {issue['title']}\n\n{issue['body']}"

    swarm = AgentSwarm()
    import asyncio
    result = asyncio.run(swarm.solve(task))

    print(f"\n📊 Result: {result.status}")
    print(f"   Agents: {', '.join(result.agents_used)}")

    # Comment on the issue with results
    if not args.dry_run:
        status_emoji = "✅" if result.status == "completed" else "⚠️"
        comment = (
            f"{status_emoji} **Agent Swarm Result**\n\n"
            f"- **Status:** {result.status}\n"
            f"- **Agents:** {', '.join(result.agents_used)}\n"
            f"- **Iterations:** {result.iterations}\n"
            f"- **Duration:** {result.duration_seconds}s\n"
        )
        gh.comment_on_issue(args.issue, comment)
        print("\n💬 Posted result to GitHub issue")


def cmd_label(args) -> None:
    """Auto-label GitHub issues using LLM classification."""
    _require_legacy_swarm_enabled("label")

    from regengine.swarm.github_integration import GitHubClient, IssueLabelClassifier
    from regengine.swarm.llm import LLMClientFactory, MockLLMClient

    print(f"🏷️  Issue Labeler — {args.repo}\n")

    if args.dry_run:
        print("🏜️  DRY RUN — labels will not be applied\n")

    gh = GitHubClient(repo_name=args.repo)

    if args.mock:
        mock_response = json.dumps({
            "categories": ["security", "bug"],
            "confidence": 0.85,
            "reasoning": "Issue mentions authentication and vulnerability",
        })
        llm = MockLLMClient(responses=[mock_response])
    else:
        llm = LLMClientFactory.create()

    classifier = IssueLabelClassifier(llm_client=llm)
    results = classifier.label_issues(
        gh,
        limit=args.limit,
        dry_run=args.dry_run,
        min_confidence=args.min_confidence,
    )

    print(f"\n{'#':<6} {'Title':<40} {'Labels':<30} {'Conf':<6} {'Applied'}")
    print("─" * 90)
    for r in results:
        title = r["title"][:38]
        labels = ", ".join(r["labels"]) or "—"
        conf = f"{r['confidence']:.0%}"
        applied = "✅" if r["applied"] else ("🏜️" if args.dry_run else "⏭️")
        print(f"#{r['issue_number']:<5} {title:<40} {labels:<30} {conf:<6} {applied}")


def cmd_status(args) -> None:
    """Show swarm status and configuration."""
    if not _legacy_swarm_enabled():
        print("RegEngine Agent Runtime Status")
        print("")
        print("Legacy autonomous swarm: disabled")
        print(f"Opt-in env: {LEGACY_SWARM_ENV}=1")
        print("Supported roles: planner, implementer, security_review")
        print("Supported helper: python3 scripts/summon_agent.py --list")
        return

    from regengine.swarm.coordinator import AgentSwarm

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🧬 RegEngine Autonomous Agent Swarm              ║")
    print("╠══════════════════════════════════════════════════════════════╣")

    swarm = AgentSwarm()
    status = swarm.status()

    print("║  Agents:                                                    ║")
    for name, info in status["agents"].items():
        print(f"║    ✅ {info['name']:<18} ({info['role']}){'':>24}║")

    print("║                                                              ║")
    print(f"║  LLM: {status['llm_provider']:<53}║")
    print(f"║  Max Iterations: {status['max_iterations']:<42}║")
    print("║                                                              ║")
    print("║  Commands:                                                   ║")
    print("║    run   --task 'description'    Solve a task                ║")
    print("║    troubleshoot --logs '...'      Heal CI failures            ║")
    print("║    solve --issue 42 --repo o/r   Solve a GitHub issue       ║")
    print("║    label --repo o/r --dry-run    Auto-label issues          ║")
    print("║    status                        Show swarm status           ║")
    print("║    sweep --limit 5               Proactively sweep tech debt ║")
    print("║    compliance --standard FSMA-204 Roll out compliance       ║")
    print("╚══════════════════════════════════════════════════════════════╝")


def cmd_sweep(args) -> None:
    """Execute a proactive sweep across horizontal technical debt."""
    _require_legacy_swarm_enabled("sweep")

    import asyncio
    from scripts.swarm_sweep import SwarmSweeper
    sweeper = SwarmSweeper()
    asyncio.run(sweeper.sweep(limit=args.limit))


def cmd_compliance(args) -> None:
    """Execute a proactive compliance rollout across the fleet."""
    _require_legacy_swarm_enabled("compliance")

    import asyncio
    from scripts.compliance_sweep import roll_out_compliance
    asyncio.run(roll_out_compliance(standard=args.standard))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RegEngine legacy autonomous agent swarm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── run ──
    run_parser = subparsers.add_parser("run", help="Run swarm on a task")
    run_parser.add_argument("--task", required=True, help="Task description")
    run_parser.add_argument("--agent", help="Direct to specific agent (e.g. security, core)")
    run_parser.add_argument("--dry-run", action="store_true", help="Use mock LLM")
    run_parser.add_argument("--max-iterations", type=int, default=3, help="Max feedback loops")
    run_parser.add_argument("--output-file", help="Save result JSON to file")
    run_parser.set_defaults(func=cmd_run)

    # ── solve ──
    solve_parser = subparsers.add_parser("solve", help="Solve a GitHub issue")
    solve_parser.add_argument("--issue", type=int, required=True, help="Issue number")
    solve_parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    solve_parser.add_argument("--dry-run", action="store_true", help="Don't post to GitHub")
    solve_parser.set_defaults(func=cmd_solve)

    # ── label ──
    label_parser = subparsers.add_parser("label", help="Auto-label GitHub issues")
    label_parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    label_parser.add_argument("--dry-run", action="store_true", help="Don't apply labels")
    label_parser.add_argument("--mock", action="store_true", help="Use mock LLM")
    label_parser.add_argument("--limit", type=int, default=10, help="Max issues to process")
    label_parser.add_argument("--min-confidence", type=float, default=0.7, help="Min confidence threshold")
    label_parser.set_defaults(func=cmd_label)

    # ── troubleshoot ──
    ts_parser = subparsers.add_parser("troubleshoot", help="Troubleshoot and fix CI failures")
    ts_parser.add_argument("--logs", help="CI failure logs/snippet (string)")
    ts_parser.add_argument("--log-file", help="Path to log file, or '-' for stdin")
    ts_parser.set_defaults(func=cmd_troubleshoot)

    # ── status ──
    status_parser = subparsers.add_parser("status", help="Show swarm status")
    status_parser.set_defaults(func=cmd_status)

    # ── compliance ──
    compliance_parser = subparsers.add_parser("compliance", help="Proactively roll out compliance standards")
    compliance_parser.add_argument("--standard", default="FSMA-204", help="Standard to roll out (FSMA-204, Finance)")
    compliance_parser.set_defaults(func=cmd_compliance)

    # ── sweep ──
    sweep_parser = subparsers.add_parser("sweep", help="Proactively sweep horizontal tech debt")
    sweep_parser.add_argument("--limit", type=int, default=5, help="Max issues to solve")
    sweep_parser.set_defaults(func=cmd_sweep)

    args = parser.parse_args()
    configure_logging(verbose=getattr(args, "verbose", False))

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
