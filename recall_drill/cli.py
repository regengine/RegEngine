"""CLI entry point for the RegEngine Recall Drill System.

Usage:
    python -m recall_drill.cli run --scenarios 10 --output drill_output
    python -m recall_drill.cli run --scenarios 100 --mutations 2 --output drill_output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from recall_drill.export.json_exporter import JSONExporter
from recall_drill.recall.orchestrator import RecallOrchestrator
from recall_drill.recall.scenario_generator import ScenarioGenerator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RegEngine FSMA 204 Recall Drill System"
    )
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("run", help="Run recall drill scenarios")
    run_cmd.add_argument(
        "--scenarios", type=int, default=10, help="Number of scenarios to generate"
    )
    run_cmd.add_argument(
        "--mutations", type=int, default=1, help="Mutations per scenario"
    )
    run_cmd.add_argument(
        "--output", type=str, default="drill_output", help="Output directory"
    )
    run_cmd.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )

    args = parser.parse_args(argv)

    if args.command != "run":
        parser.print_help()
        return 1

    print(f"Generating {args.scenarios} recall drill scenarios...")
    gen = ScenarioGenerator(seed=args.seed)
    scenarios = gen.generate_suite(
        count=args.scenarios, mutations_per_scenario=args.mutations
    )

    print(f"Running {len(scenarios)} drills...")
    orchestrator = RecallOrchestrator(output_dir=args.output, seed=args.seed)
    reports = orchestrator.run_suite(scenarios)

    # Summary
    passed = sum(1 for r in reports if r.status == "PASS")
    failed = len(reports) - passed
    avg_score = sum(r.integrity_score for r in reports) / max(len(reports), 1)

    summary = {
        "total_drills": len(reports),
        "passed": passed,
        "failed": failed,
        "avg_integrity_score": round(avg_score, 1),
        "drills": [r.to_dict() for r in reports],
    }

    summary_path = Path(args.output) / "suite_summary.json"
    JSONExporter().export_file(summary, summary_path)

    print(f"\n{'='*60}")
    print(f"  RECALL DRILL SUITE COMPLETE")
    print(f"{'='*60}")
    print(f"  Total:   {len(reports)}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Avg Score: {avg_score:.1f}/100")
    print(f"  Output:  {summary_path}")
    print(f"{'='*60}")

    for r in reports:
        icon = "PASS" if r.status == "PASS" else "FAIL"
        print(f"  [{icon}] {r.scenario_id}  score={r.integrity_score}  {r.time_to_completion}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
