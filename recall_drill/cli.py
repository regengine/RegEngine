"""CLI entry point for the RegEngine Recall Drill System.

Usage:
    python -m recall_drill run       --scenarios 10 --output drill_output
    python -m recall_drill mutate    --lots 5 --mutations 2 --output mutated.json
    python -m recall_drill validate  --input data.json
    python -m recall_drill score     --input data.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from recall_drill.export.json_exporter import JSONExporter
from recall_drill.failure_engine.generator import DatasetGenerator
from recall_drill.failure_engine.mutation_library import MutationType
from recall_drill.pipeline import PipelineConfig, RecallDrillPipeline
from recall_drill.recall.scenario_generator import ScenarioGenerator
from recall_drill.scoring.integrity_score import IntegrityScorer
from recall_drill.validation.fsma_validator import FSMAValidator

logger = logging.getLogger("recall_drill")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ------------------------------------------------------------------
# Subcommands
# ------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the full recall drill pipeline."""
    config = PipelineConfig(
        output_dir=args.output,
        seed=args.seed,
        num_scenarios=args.scenarios,
        mutations_per_scenario=args.mutations,
        pass_threshold=args.pass_threshold,
    )
    pipeline = RecallDrillPipeline(config)

    print(f"Generating {args.scenarios} recall drill scenarios...")
    gen = ScenarioGenerator(seed=args.seed)
    scenarios = gen.generate_suite(
        count=args.scenarios, mutations_per_scenario=args.mutations
    )

    print(f"Running {len(scenarios)} drills...")
    reports = pipeline.run_suite(scenarios)

    # Summary
    passed = sum(1 for r in reports if r.status == "PASS")
    failed = len(reports) - passed
    avg_score = sum(r.integrity_score for r in reports) / max(len(reports), 1)

    print(f"\n{'=' * 60}")
    print("  RECALL DRILL SUITE COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Total:       {len(reports)}")
    print(f"  Passed:      {passed}")
    print(f"  Failed:      {failed}")
    print(f"  Avg Score:   {avg_score:.1f}/100")
    print(f"  Output:      {Path(args.output) / 'suite_summary.json'}")
    print(f"{'=' * 60}")

    for r in reports:
        tag = "PASS" if r.status == "PASS" else "FAIL"
        print(f"  [{tag}] {r.scenario_id}  score={r.integrity_score}  {r.time_to_completion}")

    return 0 if failed == 0 else 1


def _cmd_mutate(args: argparse.Namespace) -> int:
    """Generate mutated datasets from clean sample data."""
    pipeline = RecallDrillPipeline(
        PipelineConfig(seed=args.seed, output_dir=args.output)
    )

    mutation_types: list[MutationType] | None = None
    if args.mutation_types:
        mutation_types = []
        for name in args.mutation_types:
            try:
                mutation_types.append(MutationType(name))
            except ValueError:
                print(f"Unknown mutation type: {name}", file=sys.stderr)
                print(f"Valid types: {[m.value for m in MutationType]}", file=sys.stderr)
                return 1

    result = pipeline.run_mutation_only(
        num_lots=args.lots,
        mutations=mutation_types,
    )

    output_path = Path(args.output) / "mutated_dataset.json"
    exporter = JSONExporter()
    exporter.export_file(result, output_path)

    print(f"Clean records:   {result['clean_record_count']}")
    print(f"Mutated records: {result['mutated_record_count']}")
    print(f"Mutations:       {result['mutations_applied']}")
    print(f"Output:          {output_path}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """Run FSMA 204 validation on a dataset."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"File not found: {input_path}", file=sys.stderr)
        return 1

    data = json.loads(input_path.read_text(encoding="utf-8"))

    # Support both raw record lists and wrapped formats
    if isinstance(data, dict):
        records = data.get("data", data.get("records", []))
    elif isinstance(data, list):
        records = data
    else:
        print("Unrecognized input format", file=sys.stderr)
        return 1

    validator = FSMAValidator()
    report = validator.validate(records)

    print(f"Records validated: {report.total_records}")
    print(f"Valid:             {report.valid}")
    print(f"Errors:            {report.error_count}")
    print(f"Warnings:          {report.warning_count}")

    if report.errors:
        print("\nErrors:")
        for err in report.errors[:20]:
            print(f"  [{err.rule}] record={err.record_index} "
                  f"field={err.field} tlc={err.tlc}: {err.message}")
        if len(report.errors) > 20:
            print(f"  ... and {len(report.errors) - 20} more errors")

    if args.output:
        exporter = JSONExporter()
        out_path = Path(args.output) / "validation_report.json"
        exporter.export_file(report.to_dict(), out_path)
        print(f"\nFull report: {out_path}")

    return 0 if report.valid else 1


def _cmd_score(args: argparse.Namespace) -> int:
    """Run integrity scoring on a dataset."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"File not found: {input_path}", file=sys.stderr)
        return 1

    data = json.loads(input_path.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        records = data.get("data", data.get("records", []))
    elif isinstance(data, list):
        records = data
    else:
        print("Unrecognized input format", file=sys.stderr)
        return 1

    pipeline = RecallDrillPipeline(PipelineConfig())
    result = pipeline.run_scoring_only(
        records=records,
        trace_gaps=args.trace_gaps,
        trace_orphans=args.trace_orphans,
    )

    print(f"Integrity Score:     {result['score']}/100  (Grade: {result['grade']})")
    print(f"  Trace Completeness:  {result['breakdown']['trace_completeness']}/25")
    print(f"  KDE Completeness:    {result['breakdown']['kde_completeness']}/25")
    print(f"  Temporal Integrity:  {result['breakdown']['temporal_integrity']}/25")
    print(f"  Pipeline Resilience: {result['breakdown']['pipeline_resilience']}/25")

    if args.output:
        exporter = JSONExporter()
        out_path = Path(args.output) / "integrity_score.json"
        exporter.export_file(result, out_path)
        print(f"\nFull report: {out_path}")

    return 0


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="recall_drill",
        description="RegEngine FSMA 204 Recall Drill System",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    sub = parser.add_subparsers(dest="command")

    # --- run ---
    run_cmd = sub.add_parser("run", help="Run full recall drill pipeline")
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
    run_cmd.add_argument(
        "--pass-threshold", type=int, default=80,
        help="Minimum integrity score to pass (0-100)",
    )

    # --- mutate ---
    mut_cmd = sub.add_parser("mutate", help="Generate mutated datasets")
    mut_cmd.add_argument(
        "--lots", type=int, default=5, help="Number of lots to generate"
    )
    mut_cmd.add_argument(
        "--mutation-types", nargs="*", default=None,
        help="Specific mutation types to apply (e.g., duplicate_tlc shuffle_timestamps)",
    )
    mut_cmd.add_argument(
        "--output", type=str, default="drill_output", help="Output directory"
    )
    mut_cmd.add_argument("--seed", type=int, default=42, help="Random seed")

    # --- validate ---
    val_cmd = sub.add_parser("validate", help="Run FSMA 204 validation on a dataset")
    val_cmd.add_argument(
        "--input", type=str, required=True, help="Path to JSON dataset file"
    )
    val_cmd.add_argument(
        "--output", type=str, default=None, help="Output directory for report"
    )

    # --- score ---
    score_cmd = sub.add_parser("score", help="Run integrity scoring on a dataset")
    score_cmd.add_argument(
        "--input", type=str, required=True, help="Path to JSON dataset file"
    )
    score_cmd.add_argument(
        "--output", type=str, default=None, help="Output directory for report"
    )
    score_cmd.add_argument(
        "--trace-gaps", type=int, default=0,
        help="Number of known trace gaps (from graph analysis)",
    )
    score_cmd.add_argument(
        "--trace-orphans", type=int, default=0,
        help="Number of known orphan records (from graph analysis)",
    )

    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))

    dispatch = {
        "run": _cmd_run,
        "mutate": _cmd_mutate,
        "validate": _cmd_validate,
        "score": _cmd_score,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
