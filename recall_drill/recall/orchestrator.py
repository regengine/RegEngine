"""Recall drill orchestrator — runs the full pipeline end-to-end."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recall_drill.debug.root_cause import DebugEngine, DebugReport
from recall_drill.export.csv_exporter import CSVExporter
from recall_drill.export.json_exporter import JSONExporter
from recall_drill.failure_engine.mutator import MutationResult, Mutator
from recall_drill.recall.scenario_generator import RecallScenario
from recall_drill.recall.timer import SLATimer
from recall_drill.scoring.integrity_score import IntegrityScore, IntegrityScorer
from recall_drill.validation.fsma_validator import FSMAValidator, ValidationReport


@dataclass
class DrillReport:
    scenario_id: str
    mutation_id: str | None
    time_to_completion: str
    status: str  # PASS | FAIL
    integrity_score: int
    score_breakdown: dict
    validation: dict
    failures: list[dict]
    export_path: str
    root_cause: dict
    sla: dict

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "mutation_id": self.mutation_id,
            "time_to_completion": self.time_to_completion,
            "status": self.status,
            "integrity_score": self.integrity_score,
            "score_breakdown": self.score_breakdown,
            "validation": self.validation,
            "failures": self.failures,
            "export_path": self.export_path,
            "root_cause": self.root_cause,
            "sla": self.sla,
        }


class RecallOrchestrator:
    """Run a complete recall drill: mutate -> validate -> export -> score -> debug."""

    def __init__(self, output_dir: str = "drill_output", seed: int = 42):
        self._output = Path(output_dir)
        self._mutator = Mutator(seed=seed)
        self._validator = FSMAValidator()
        self._scorer = IntegrityScorer()
        self._csv = CSVExporter()
        self._json = JSONExporter()
        self._debug = DebugEngine()

    def run(self, scenario: RecallScenario) -> DrillReport:
        """Execute a single recall drill scenario."""
        timer = SLATimer()
        timer.start()

        # 1. Apply mutations
        data = scenario.dataset
        mutation_meta: dict | None = None

        for mutation_type in scenario.mutations:
            fn_name = mutation_type.value
            fn = getattr(self._mutator, fn_name, None)
            if fn is None:
                continue

            # Dataset-level mutations take list, record-level take dict
            if fn_name in (
                "remove_required_field", "corrupt_type", "missing_supplier"
            ):
                if data:
                    import random
                    idx = random.Random(42).randrange(len(data))
                    if fn_name == "corrupt_type":
                        result = fn(data[idx], "quantity")
                    else:
                        result = fn(data[idx])
                    data[idx] = result.data
                    mutation_meta = result.metadata
            else:
                result = fn(data)
                data = result.data if isinstance(result.data, list) else data
                mutation_meta = result.metadata

        # 2. Validate
        validation = self._validator.validate(data)

        # 3. Export
        scenario_dir = self._output / scenario.scenario_id
        csv_path = self._csv.export_file(data, scenario_dir / "fda_204_export.csv")

        # 4. Score
        score = self._scorer.score(
            validation=validation,
            records=data,
            trace_gaps=0,
            trace_orphans=0,
            injection_success_rate=1.0,
        )

        # 5. Debug
        debug_report = self._debug.analyze(
            scenario_id=scenario.scenario_id,
            mutation_metadata=mutation_meta,
            validation=validation,
            records=data,
        )

        timer.stop()

        # 6. Build report
        status = "PASS" if validation.valid and score.score >= 80 else "FAIL"
        report = DrillReport(
            scenario_id=scenario.scenario_id,
            mutation_id=mutation_meta.get("mutation_id") if mutation_meta else None,
            time_to_completion=f"{timer.elapsed:.3f}s",
            status=status,
            integrity_score=score.score,
            score_breakdown=score.to_dict()["breakdown"],
            validation=validation.to_dict(),
            failures=[e.to_dict() for e in validation.errors],
            export_path=csv_path,
            root_cause=debug_report.to_dict(),
            sla=timer.to_dict(),
        )

        # 7. Save full report
        self._json.export_file(
            report.to_dict(), scenario_dir / "drill_report.json"
        )

        return report

    def run_suite(self, scenarios: list[RecallScenario]) -> list[DrillReport]:
        """Run an entire suite of scenarios and return all reports."""
        reports = []
        for scenario in scenarios:
            report = self.run(scenario)
            reports.append(report)
        return reports
