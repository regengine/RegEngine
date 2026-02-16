"""CLI entry point for the autonomous agent swarm.

Usage:
    python -m regengine.swarm run --task "Add rate limiting to /api/ingest"
    python -m regengine.swarm solve --issue 42 --repo owner/repo
    python -m regengine.swarm label --repo owner/repo --dry-run
    python -m regengine.swarm status
"""

import argparse
import json
import sys
from typing import Optional

import structlog


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
    
    if args.agent:
        print(f"🕵️  Directing task to: {args.agent}\n")
        agent_instance = swarm.agents.get(args.agent)
        if not agent_instance:
            print(f"❌ Error: Agent '{args.agent}' not found. Available: {list(swarm.agents.keys())}")
            sys.exit(1)
        
        # Security audit logic for direct agent call
        if args.agent == "security":
            result_data = agent_instance.run(args.task)
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

        result = swarm.solve(args.task)
    else:
        result = swarm.solve(args.task)

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
    import asyncio
    from regengine.swarm.coordinator import AgentSwarm
    
    print(f"🧬 CI Resilience Agent — Analyzing logs...\n")
    
    swarm = AgentSwarm()
    # Troubleshoot is async in coordinator
    result = asyncio.run(swarm.troubleshoot(args.logs))
    
    print("\n" + "═" * 60)
    print(f"📊 Diagnosis: {result.status}")
    print(f"   Root Cause: {result.plan.get('root_cause') if result.plan else 'Unknown'}")
    print(f"   Remediation: {result.plan.get('immediate_fix') if result.plan else 'None'}")
    print(f"   Agents: {', '.join(result.agents_used)}")
    print(f"   Duration: {result.duration_seconds}s")


def cmd_solve(args) -> None:
    """Solve a GitHub issue using the agent swarm."""
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
    result = swarm.solve(task)

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
    from regengine.swarm.coordinator import AgentSwarm
    from regengine.swarm.llm import LLMClientFactory

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
    print("╚══════════════════════════════════════════════════════════════╝")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RegEngine Autonomous Agent Swarm",
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
    ts_parser.add_argument("--logs", required=True, help="CI failure logs/snippet")
    ts_parser.set_defaults(func=cmd_troubleshoot)

    # ── status ──
    status_parser = subparsers.add_parser("status", help="Show swarm status")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    configure_logging(verbose=getattr(args, "verbose", False))

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
