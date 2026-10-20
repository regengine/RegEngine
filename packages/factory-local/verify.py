"""Z3 verification of the status logic, built from the IR (not from Rego text).

The status bodies here mirror compiler.py line for line. Two properties:
  deterministic  every pair of status bodies is disjoint (no OPA conflict)
  complete       Not(Or(bodies)) is UNSAT (every input gets a status)

A well formed IR under strict precedence satisfies both by construction; the
check exists to catch drift between this file, compiler.py and future IR
features. check_status_bodies() is exposed so drifted bodies can be tested.
"""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

import z3

from schemas import DeonticIR, Modality, Operator

STATUSES = ("COMPLIANT", "COMPLIANT_VIA_SAFE_HARBOR", "NON_COMPLIANT_BREACH", "EXEMPT_OR_NOT_APPLICABLE")
OK_STATUS = "UNSAT_DETERMINISTIC_AND_COMPLETE"


def _sort_of(value) -> str:
    if isinstance(value, bool):
        return "Bool"
    if isinstance(value, int):
        return "Int"
    if isinstance(value, float):
        return "Real"
    return "String"


def _fact_sorts(irs: Iterable[DeonticIR]) -> dict[str, str]:
    """One Z3 sort per fact across all IRs. Int widens to Real; other mixes are errors."""
    sorts: dict[str, str] = {}
    for ir in irs:
        for p in ir.applicability_predicates:
            new = _sort_of(p.value)
            old = sorts.get(p.fact)
            if old is None or old == new:
                sorts[p.fact] = new
            elif {old, new} == {"Int", "Real"}:
                sorts[p.fact] = "Real"
            else:
                raise ValueError(f"fact {p.fact!r} used as both {old} and {new}")
    return sorts


def _make_vars(irs: list[DeonticIR]) -> dict[str, z3.ExprRef]:
    ctor = {"Bool": z3.Bool, "Int": z3.Int, "Real": z3.Real, "String": z3.String}
    env = {fact: ctor[sort](fact) for fact, sort in _fact_sorts(irs).items()}
    for ir in irs:
        for control in (ir.action_required, ir.safe_harbor_control):
            env.setdefault(f"controls.{control}", z3.Bool(f"controls.{control}"))
    return env


def _value(v, sort: str):
    if sort == "Bool":
        return z3.BoolVal(v)
    if sort == "Int":
        return z3.IntVal(v)
    if sort == "Real":
        return z3.RealVal(v)
    return z3.StringVal(v)


def applicability(ir: DeonticIR, env: dict) -> z3.BoolRef:
    terms = []
    for p in ir.applicability_predicates:
        var = env[p.fact]
        val = _value(p.value, var.sort().name() if not z3.is_string(var) else "String")
        if p.operator == Operator.GREATER_THAN:
            terms.append(var > val)
        elif p.operator == Operator.LESS_THAN:
            terms.append(var < val)
        else:
            terms.append(var == val)
    return z3.And(terms) if terms else z3.BoolVal(True)


def status_bodies(ir: DeonticIR, env: dict | None = None) -> tuple[dict[str, z3.BoolRef], dict]:
    env = env if env is not None else _make_vars([ir])
    app = applicability(ir, env)
    control = env[f"controls.{ir.action_required}"]
    act = control if ir.modality == Modality.OBLIGATION else z3.Not(control)
    sh = env[f"controls.{ir.safe_harbor_control}"]
    bodies = {
        "COMPLIANT": z3.And(app, act),
        "COMPLIANT_VIA_SAFE_HARBOR": z3.And(app, z3.Not(act), sh),
        "NON_COMPLIANT_BREACH": z3.And(app, z3.Not(act), z3.Not(sh)),
        "EXEMPT_OR_NOT_APPLICABLE": z3.Not(app),
    }
    return bodies, env


def _py(val):
    if z3.is_true(val):
        return True
    if z3.is_false(val):
        return False
    if z3.is_int_value(val):
        return val.as_long()
    if z3.is_rational_value(val):
        frac = val.as_fraction()
        return int(frac) if frac.denominator == 1 else float(frac)
    if z3.is_string_value(val):
        return val.as_string()
    return str(val)


def model_to_dict(model: z3.ModelRef, env: dict) -> dict:
    return {name: _py(model.eval(var, model_completion=True)) for name, var in sorted(env.items())}


def check_status_bodies(bodies: dict[str, z3.BoolRef], env: dict) -> dict:
    overlaps = []
    for a, b in combinations(bodies, 2):
        s = z3.Solver()
        s.add(z3.And(bodies[a], bodies[b]))
        if s.check() == z3.sat:
            overlaps.append({"statuses": [a, b], "counterexample": model_to_dict(s.model(), env)})

    s = z3.Solver()
    s.add(z3.Not(z3.Or(list(bodies.values()))))
    gap = model_to_dict(s.model(), env) if s.check() == z3.sat else None

    deterministic, complete = not overlaps, gap is None
    if deterministic and complete:
        status = OK_STATUS
    elif not deterministic:
        status = "SAT_OVERLAP" if complete else "SAT_OVERLAP_AND_GAP"
    else:
        status = "SAT_GAP"
    return {
        "status": status,
        "deterministic": deterministic,
        "complete": complete,
        "overlaps": overlaps,
        "gap_counterexample": gap,
        "z3_version": z3.get_version_string(),
    }


def verify_ir(ir: DeonticIR) -> dict:
    bodies, env = status_bodies(ir)
    return {"rule_id": ir.rule_id, **check_status_bodies(bodies, env)}


def check_cross_rule_collisions(irs: list[DeonticIR]) -> list[dict]:
    """For each ordered pair sharing a fact, find inputs where one rule is exempt
    and the other is obligated (applicable). Each hit carries a concrete model."""
    collisions = []
    for a, b in combinations(irs, 2):
        shared = sorted({p.fact for p in a.applicability_predicates} & {p.fact for p in b.applicability_predicates})
        if not shared:
            continue
        try:
            env = _make_vars([a, b])
        except ValueError as exc:
            collisions.append({"rules": [a.rule_id, b.rule_id], "shared_facts": shared, "type_conflict": str(exc)})
            continue
        app = {a.rule_id: applicability(a, env), b.rule_id: applicability(b, env)}
        for exempt, obligated in ((a, b), (b, a)):
            s = z3.Solver()
            s.add(z3.Not(app[exempt.rule_id]), app[obligated.rule_id])
            if s.check() == z3.sat:
                collisions.append(
                    {
                        "exempt_rule": exempt.rule_id,
                        "obligated_rule": obligated.rule_id,
                        "shared_facts": shared,
                        "model": model_to_dict(s.model(), env),
                    }
                )
    return collisions
