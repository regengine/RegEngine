"""Chain-health gate for alembic/versions (static, no database).

The CI script ``scripts/check_alembic_revisions.py`` already rejects
duplicate revisions, orphan down_revisions and multiple heads, but it parses
the files with its own regex/AST helpers. If that parser ever drifts from
what Alembic itself understands (for example a new down_revision shape it
does not recognise), the script could report one head while ``alembic
upgrade head`` sees several and every deploy fails. These tests pin the real
chain to Alembic's own ``ScriptDirectory`` reading, so the two can never
silently disagree:

1. Alembic sees exactly one head.
2. The CI script's parser agrees with Alembic on the head set.
3. Every down_revision pointer resolves to a real revision.
4. Every revision file defines both ``upgrade()`` and ``downgrade()``.
5. Merge revisions keep ``pass`` downgrades (a merge downgrade runs before
   the branch downgrades beneath it, so real work there is ordered
   dangerously).
"""

from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"


def _scripts() -> ScriptDirectory:
    cfg = Config()
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _downgrade_fn(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "downgrade":
            return node
    return None


def _is_pass_only(fn) -> bool:
    body = [node for node in fn.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def test_single_head() -> None:
    """Alembic itself must see exactly one head, or deploys die on ambiguity."""
    heads = _scripts().get_heads()
    assert len(heads) == 1, f"expected exactly one alembic head, found {len(heads)}: {sorted(heads)}"


def test_check_script_agrees_with_alembic_on_heads() -> None:
    """The CI gate's parser must resolve the same head Alembic does."""
    import importlib.util

    script_path = REPO_ROOT / "scripts" / "check_alembic_revisions.py"
    spec = importlib.util.spec_from_file_location("check_alembic_revisions", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    down_rows = mod.collect_down_revisions()
    rev_ids = {rev for _, rev, _ in down_rows}
    pointed_at = {down for _, _, downs in down_rows for down in downs}
    script_heads = sorted(rev_ids - pointed_at)
    alembic_heads = sorted(_scripts().get_heads())
    assert script_heads == alembic_heads, (
        f"check_alembic_revisions.py resolves heads {script_heads} but Alembic resolves "
        f"{alembic_heads}; the gate parser has drifted from a down_revision shape in the chain"
    )


def test_no_orphan_down_revisions() -> None:
    """Every down_revision pointer must resolve to a revision Alembic knows."""
    scripts = _scripts()
    orphans = []
    for sc in scripts.walk_revisions():
        downs = sc.down_revision
        if downs is None:
            continue
        if isinstance(downs, str):
            downs = (downs,)
        for down in downs:
            if scripts.get_revision(down) is None:
                orphans.append(f"{sc.revision} -> {down}")
    assert not orphans, f"down_revisions with no matching revision file: {orphans}"


def test_every_revision_defines_upgrade_and_downgrade() -> None:
    """A revision without downgrade() breaks ``alembic downgrade`` walk-back."""
    missing = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        absent = {"upgrade", "downgrade"} - names
        if absent:
            missing.append(f"{path.name} lacks {sorted(absent)}")
    assert not missing, f"revisions missing entry points: {missing}"


def test_merge_revisions_keep_pass_downgrades() -> None:
    """Merge points must not do real work on the way down.

    Downgrading through a merge runs the merge's downgrade() before the
    branch downgrades beneath it, so anything beyond ``pass`` there runs
    against a half-downgraded schema. Every merge in the chain today is
    pass-only; this locks that convention in.
    """
    scripts = _scripts()
    offenders = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rev = None
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    [t.id for t in node.targets if isinstance(t, ast.Name)]
                    if isinstance(node, ast.Assign)
                    else ([node.target.id] if isinstance(node.target, ast.Name) else [])
                )
                if "revision" in targets and "down_revision" not in targets:
                    try:
                        rev = ast.literal_eval(node.value)
                    except (SyntaxError, ValueError):
                        rev = None
        if rev is None:
            continue
        sc = scripts.get_revision(rev)
        is_merge = sc is not None and sc.down_revision is not None and not isinstance(sc.down_revision, str)
        if not is_merge:
            continue
        fn = _downgrade_fn(tree)
        assert fn is not None, f"merge {path.name} has no downgrade()"
        if not _is_pass_only(fn):
            offenders.append(path.name)
    assert not offenders, f"merge revisions with real downgrade work: {offenders}"
