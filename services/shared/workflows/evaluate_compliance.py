"""
Workflow: Compliance Evaluation Pipeline

Evaluates canonical traceability events against FSMA 204 rules.
This is the core decision engine — it determines whether events
are compliant, what's missing, and what severity to assign.

Pipeline:
    1. Load active rules from fsma.rule_definitions
    2. Filter to applicable rules (by CTE type)
    3. Evaluate each rule against event data (pure logic)
    4. Aggregate results into EvaluationSummary
    5. [Optional] Persist evaluation results to DB
    6. Return pass/fail/warn with explanations

Pure logic vs I/O:
    The evaluate_event() method has a `persist` flag. When persist=False,
    it is PURE — no side effects, deterministic output for deterministic input.
    When persist=True (default), it writes to fsma.rule_evaluation_results.

    This is the pattern the PRD targets: the decision logic IS separable
    from persistence. The `persist` flag already exists — callers should
    be explicit about which mode they need.

Entry point:
    services/shared/rules/engine.py
        RulesEngine.evaluate_event()        — single event (line 96)
        RulesEngine.evaluate_events_batch() — batch (line 143)

    Rule loading: RulesEngine.load_active_rules()  — from DB (line 40)
    Rule filtering: RulesEngine.get_applicable_rules()  — by CTE type (line 75)

    Evaluators (pure functions, no I/O):
        services/shared/rules/evaluators.py — EVALUATORS dict
        services/shared/rules/relational.py — RELATIONAL_EVALUATORS dict

    Rule definitions (seed data):
        services/shared/rules/seeds.py — FSMA_RULE_SEEDS

API trigger:
    services/ingestion/app/rules_router.py
        evaluate_event()  — POST endpoint (line 185)

Side effects (explicit, only when persist=True):
    - DB write: fsma.rule_evaluation_results

Known issues:
    - RELATIONAL_EVALUATORS may have implicit DB reads for cross-entity
      checks. These are read-only but still I/O — not fully pure.
    - No structured logging at evaluation boundaries yet (Phase 6 target).
"""
