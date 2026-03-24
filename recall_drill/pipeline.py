"""Full recall drill pipeline — connects all modules into a runnable end-to-end flow.

Pipeline stages:
  1. Load / generate clean dataset
  2. Apply mutations (failure injection)
  3. Inject into API or stream (optional, skipped in offline mode)
  4. Run recall drill (trace, validate, export)
  5. Validate against FSMA 204 rules
  6. Export FDA-ready CSV + EPCIS 2.0 JSON
  7. Score system integrity
  8. Debug any failures (root-cause analysis)
  9. Output full drill report
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recall_drill.debug.root_cause import DebugEngine, DebugReport
from recall_drill.export.csv_exporter import CSVExporter
from recall_drill.export.json_exporter import JSONExporter
from recall_drill.failure_engine.generator import DatasetGenerator
from recall_drill.failure_engine.mutation_library import MutationType
from recall_drill.failure_engine.mutator import MutationResult, Mutator
from recall_drill.injection.stream_runner import StreamConfig, StreamRunner
from recall_drill.recall.scenario_generator import (
    RecallScenario,
    RecallTrigger,
    ScenarioGenerator,
)
from recall_drill.recall.timer import SLATimer
from recall_drill.scoring.integrity_score import IntegrityScore, IntegrityScorer
from recall_drill.validation.fsma_validator import FSMAValidator, ValidationReport

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the full recall drill pipeline."""

    output_dir: str = "drill_output"
    seed: int = 42
    num_scenarios: int = 10
    mutations_per_scenario: int = 1
    num_lots: int = 5
    chain_depth: int = 4
    inject_to_api: bool = False
    api_base_url: str = "http://localhost:8000"
    inject_to_stream: bool = False
    stream_config: StreamConfig | None = None
    sla_seconds: float = 86_400
    pass_threshold: int = 80


@dataclass
class StageResult:
    """Result of a single pipeline stage."""

    stage: str
    success: bool
    duration_ms: float
    detail: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class PipelineReport:
    """Complete output of one pipeline execution."""

    scenario_id: str
    mutation_ids: list[str]
    time_to_completion: str
    status: str  # PASS | FAIL
    integrity_score: int
    score_breakdown: dict
    validation: dict
    failures: list[dict]
    export_path: str
    root_cause: dict
    sla: dict
    stages: list[dict]
    started_at: str
    completed_at: str

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "mutation_id": self.mutation_ids[0] if self.mutation_ids else None,
            "mutation_ids": self.mutation_ids,
            "time_to_completion": self.time_to_completion,
            "status": self.status,
            "integrity_score": self.integrity_score,
            "score_breakdown": self.score_breakdown,
            "validation": self.validation,
            "failures": self.failures,
            "export_path": self.export_path,
            "root_cause": self.root_cause,
            "sla": self.sla,
            "stages": self.stages,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class RecallDrillPipeline:
    """Orchestrate the full recall drill pipeline.

    This is the top-level entry point that wires together every
    sub-system: dataset generation, mutation, injection, validation,
    export, scoring, and root-cause analysis.
    """

    def __init__(self, config: PipelineConfig | None = None):
        self._config = config or PipelineConfig()
        self._output = Path(self._config.output_dir)
        self._mutator = Mutator(seed=self._config.seed)
        self._validator = FSMAValidator()
        self._scorer = IntegrityScorer()
        self._csv = CSVExporter()
        self._json = JSONExporter()
        self._debug = DebugEngine()
        self._scenario_gen = ScenarioGenerator(seed=self._config.seed)
        self._stream_runner: StreamRunner | None = None

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _stage_generate(self, scenario: RecallScenario) -> tuple[list[dict], StageResult]:
        """Stage 1: Return the clean dataset from the scenario."""
        import time

        start = time.perf_counter()
        data = list(scenario.dataset)
        duration = (time.perf_counter() - start) * 1000
        return data, StageResult(
            stage="generate",
            success=True,
            duration_ms=round(duration, 2),
            detail={"record_count": len(data)},
        )

    def _stage_mutate(
        self, data: list[dict], mutations: list[MutationType]
    ) -> tuple[list[dict], list[dict], StageResult]:
        """Stage 2: Apply mutations to the dataset."""
        import time

        start = time.perf_counter()
        mutation_metas: list[dict] = []

        for mutation_type in mutations:
            fn_name = mutation_type.value
            fn = getattr(self._mutator, fn_name, None)
            if fn is None:
                logger.warning("Unknown mutation function: %s", fn_name)
                continue

            # Record-level mutations apply to a random record
            if fn_name in ("remove_required_field", "corrupt_type", "missing_supplier", "invalid_gln"):
                if data:
                    import random

                    idx = random.Random(self._config.seed).randrange(len(data))
                    if fn_name == "corrupt_type":
                        result: MutationResult = fn(data[idx], "quantity")
                    else:
                        result = fn(data[idx])
                    data[idx] = result.data
                    mutation_metas.append(result.metadata)
            elif fn_name in ("inject_encoding_errors", "encoding_error"):
                # Encoding errors apply to CSV text, skip for dataset mutations
                logger.info("Skipping encoding_error mutation (CSV-only)")
                continue
            else:
                result = fn(data)
                if isinstance(result.data, list):
                    data = result.data
                mutation_metas.append(result.metadata)

        duration = (time.perf_counter() - start) * 1000
        return (
            data,
            mutation_metas,
            StageResult(
                stage="mutate",
                success=True,
                duration_ms=round(duration, 2),
                detail={
                    "mutations_applied": len(mutation_metas),
                    "mutation_types": [m.get("type") for m in mutation_metas],
                },
            ),
        )

    def _stage_inject(
        self, data: list[dict], mutation_metas: list[dict]
    ) -> StageResult:
        """Stage 3: Inject data into API / stream (optional)."""
        import time

        start = time.perf_counter()
        injection_detail: dict[str, Any] = {"mode": "offline"}

        if self._config.inject_to_stream:
            if self._stream_runner is None:
                self._stream_runner = StreamRunner(
                    config=self._config.stream_config, dry_run=True
                )
            mid = mutation_metas[0].get("mutation_id") if mutation_metas else None
            result = self._stream_runner.produce_batch(data, mutation_id=mid)
            injection_detail = {
                "mode": "stream",
                "total": result.total_messages,
                "success": result.success_count,
                "failure": result.failure_count,
            }

        duration = (time.perf_counter() - start) * 1000
        return StageResult(
            stage="inject",
            success=True,
            duration_ms=round(duration, 2),
            detail=injection_detail,
        )

    def _stage_validate(
        self, data: list[dict]
    ) -> tuple[ValidationReport, StageResult]:
        """Stage 5: Run FSMA 204 validation."""
        import time

        start = time.perf_counter()
        validation = self._validator.validate(data)
        duration = (time.perf_counter() - start) * 1000
        return validation, StageResult(
            stage="validate",
            success=True,
            duration_ms=round(duration, 2),
            detail={
                "valid": validation.valid,
                "errors": validation.error_count,
                "warnings": validation.warning_count,
            },
        )

    def _stage_export(
        self, data: list[dict], scenario_id: str
    ) -> tuple[str, StageResult]:
        """Stage 6: Export FDA-ready CSV and EPCIS 2.0 JSON."""
        import time

        start = time.perf_counter()
        scenario_dir = self._output / scenario_id
        csv_path = self._csv.export_file(data, scenario_dir / "fda_204_export.csv")
        epcis_path = self._json.export_epcis_file(
            data, scenario_dir / "epcis_2.0_export.json"
        )
        duration = (time.perf_counter() - start) * 1000
        return csv_path, StageResult(
            stage="export",
            success=True,
            duration_ms=round(duration, 2),
            detail={"csv_path": csv_path, "epcis_path": epcis_path},
        )

    def _stage_score(
        self,
        validation: ValidationReport,
        data: list[dict],
        injection_success_rate: float = 1.0,
    ) -> tuple[IntegrityScore, StageResult]:
        """Stage 7: Calculate integrity score."""
        import time

        start = time.perf_counter()
        score = self._scorer.score(
            validation=validation,
            records=data,
            trace_gaps=0,
            trace_orphans=0,
            injection_success_rate=injection_success_rate,
        )
        duration = (time.perf_counter() - start) * 1000
        return score, StageResult(
            stage="score",
            success=True,
            duration_ms=round(duration, 2),
            detail=score.to_dict(),
        )

    def _stage_debug(
        self,
        scenario_id: str,
        mutation_metas: list[dict],
        validation: ValidationReport,
        data: list[dict],
    ) -> tuple[DebugReport, StageResult]:
        """Stage 8: Root-cause analysis on failures."""
        import time

        start = time.perf_counter()
        # Use the last mutation metadata for primary attribution
        primary_meta = mutation_metas[-1] if mutation_metas else None
        debug_report = self._debug.analyze(
            scenario_id=scenario_id,
            mutation_metadata=primary_meta,
            validation=validation,
            records=data,
        )
        duration = (time.perf_counter() - start) * 1000
        return debug_report, StageResult(
            stage="debug",
            success=True,
            duration_ms=round(duration, 2),
            detail={
                "root_cause_count": len(debug_report.root_causes),
                "summary": debug_report.summary,
            },
        )

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run_scenario(self, scenario: RecallScenario) -> PipelineReport:
        """Execute the full pipeline for a single scenario."""
        started_at = datetime.now(timezone.utc).isoformat()
        timer = SLATimer(sla_seconds=self._config.sla_seconds)
        timer.start()
        stages: list[StageResult] = []

        # 1. Generate / load dataset
        data, gen_stage = self._stage_generate(scenario)
        stages.append(gen_stage)

        # 2. Apply mutations
        data, mutation_metas, mut_stage = self._stage_mutate(
            data, scenario.mutations
        )
        stages.append(mut_stage)

        # 3. Inject (optional)
        inject_stage = self._stage_inject(data, mutation_metas)
        stages.append(inject_stage)

        # 4. (Trace query would go here with live Neo4j — skipped in offline mode)

        # 5. Validate
        validation, val_stage = self._stage_validate(data)
        stages.append(val_stage)

        # 6. Export
        csv_path, export_stage = self._stage_export(data, scenario.scenario_id)
        stages.append(export_stage)

        # 7. Score
        score, score_stage = self._stage_score(validation, data)
        stages.append(score_stage)

        # 8. Debug
        debug_report, debug_stage = self._stage_debug(
            scenario.scenario_id, mutation_metas, validation, data
        )
        stages.append(debug_stage)

        timer.stop()
        completed_at = datetime.now(timezone.utc).isoformat()

        # 9. Build final report
        status = (
            "PASS"
            if validation.valid and score.score >= self._config.pass_threshold
            else "FAIL"
        )

        mutation_ids = [m.get("mutation_id", "") for m in mutation_metas]

        report = PipelineReport(
            scenario_id=scenario.scenario_id,
            mutation_ids=mutation_ids,
            time_to_completion=f"{timer.elapsed:.3f}s",
            status=status,
            integrity_score=score.score,
            score_breakdown=score.to_dict()["breakdown"],
            validation=validation.to_dict(),
            failures=[e.to_dict() for e in validation.errors],
            export_path=csv_path,
            root_cause=debug_report.to_dict(),
            sla=timer.to_dict(),
            stages=[
                {
                    "stage": s.stage,
                    "success": s.success,
                    "duration_ms": s.duration_ms,
                    "detail": s.detail,
                }
                for s in stages
            ],
            started_at=started_at,
            completed_at=completed_at,
        )

        # Persist the report
        report_path = self._output / scenario.scenario_id / "drill_report.json"
        self._json.export_file(report.to_dict(), report_path)

        logger.info(
            "Pipeline complete: scenario=%s status=%s score=%d elapsed=%s",
            scenario.scenario_id,
            status,
            score.score,
            report.time_to_completion,
        )

        return report

    def run_suite(
        self, scenarios: list[RecallScenario] | None = None
    ) -> list[PipelineReport]:
        """Run the full pipeline for a suite of scenarios.

        If *scenarios* is ``None``, generates a new suite using the
        configured parameters.
        """
        if scenarios is None:
            scenarios = self._scenario_gen.generate_suite(
                count=self._config.num_scenarios,
                mutations_per_scenario=self._config.mutations_per_scenario,
            )

        reports: list[PipelineReport] = []
        for i, scenario in enumerate(scenarios, 1):
            logger.info(
                "Running scenario %d/%d: %s", i, len(scenarios), scenario.scenario_id
            )
            report = self.run_scenario(scenario)
            reports.append(report)

        # Write suite summary
        passed = sum(1 for r in reports if r.status == "PASS")
        failed = len(reports) - passed
        avg_score = sum(r.integrity_score for r in reports) / max(len(reports), 1)

        summary = {
            "suite_id": f"SUITE-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
            "total_drills": len(reports),
            "passed": passed,
            "failed": failed,
            "avg_integrity_score": round(avg_score, 1),
            "drills": [r.to_dict() for r in reports],
        }

        summary_path = self._output / "suite_summary.json"
        self._json.export_file(summary, summary_path)
        logger.info(
            "Suite complete: %d/%d passed, avg_score=%.1f",
            passed,
            len(reports),
            avg_score,
        )

        return reports

    def run_mutation_only(
        self,
        num_lots: int = 5,
        mutations: list[MutationType] | None = None,
    ) -> dict:
        """Run only the mutation stage and return the mutated dataset.

        Useful for generating test fixtures or inspecting mutation output
        without the full pipeline overhead.
        """
        gen = DatasetGenerator(seed=self._config.seed)
        clean = gen.generate_supply_chain(num_lots=num_lots)

        target_mutations = mutations or list(MutationType)[:3]
        data, metas, _ = self._stage_mutate(clean, target_mutations)

        return {
            "clean_record_count": len(clean),
            "mutated_record_count": len(data),
            "mutations_applied": [m.get("type") for m in metas],
            "mutation_metadata": metas,
            "data": data,
        }

    def run_validation_only(self, records: list[dict]) -> dict:
        """Run only the FSMA 204 validation stage."""
        validation = self._validator.validate(records)
        return validation.to_dict()

    def run_scoring_only(
        self,
        records: list[dict],
        trace_gaps: int = 0,
        trace_orphans: int = 0,
    ) -> dict:
        """Run only the integrity scoring stage."""
        validation = self._validator.validate(records)
        score = self._scorer.score(
            validation=validation,
            records=records,
            trace_gaps=trace_gaps,
            trace_orphans=trace_orphans,
        )
        return score.to_dict()
