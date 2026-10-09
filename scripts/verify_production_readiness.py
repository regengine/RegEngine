#!/usr/bin/env python3
"""
Production Readiness Verification Script for RegEngine

This script verifies that all critical production-ready fixes are in place:
1. Texas scraper uses inheritance from GenericRSSScraper
2. Correlation ID middleware is implemented
3. Brute-force rate limiting supports Redis-backed shared counters
4. Railway deployment workflow is configured

Usage:
    python scripts/verify_production_readiness.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import Callable, Iterator

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is pinned in requirements.lock
    yaml = None  # type: ignore[assignment]

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


class VerificationResult:
    """Result of a verification check."""

    def __init__(self, name: str, passed: bool, message: str, details: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details

    def __str__(self) -> str:
        status = f"{GREEN}✓ PASS{RESET}" if self.passed else f"{RED}✗ FAIL{RESET}"
        result = f"{status} - {self.name}\n  {self.message}"
        if self.details:
            result += f"\n  {YELLOW}Details:{RESET} {self.details}"
        return result


def _python_code_facts(source: str) -> tuple[set[str], set[str], dict[str, set[str]], set[str]]:
    """Structural facts about Python source, ignoring comments.

    Returns (assigned_names, function_names, methods_by_class, string_literals)
    where assigned_names are targets of real assignments, function_names are
    every defined function (including methods), methods_by_class maps each
    class name to the methods defined directly in its body, and
    string_literals are the exact string constants in the code. A token that
    appears only in a comment or docstring-adjacent prose never lands in the
    first three sets, and only an exact string literal lands in the last one.
    """
    tree = ast.parse(source)
    assigned: set[str] = set()
    functions: set[str] = set()
    methods: dict[str, set[str]] = {}
    strings: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            methods[node.name] = {
                item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                assigned.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            assigned.update(n.id for n in ast.walk(node.target) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            assigned.update(n.id for n in ast.walk(node.target) if isinstance(n, ast.Name))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)

    return assigned, functions, methods, strings


def _iter_yaml_strings(node: object, parent_key: str | None = None) -> Iterator[tuple[str | None, str]]:
    """Yield (parent_key, string) for every mapping key and scalar in parsed YAML.

    Comments never reach here because the YAML parser drops them, so a token
    that appears only in a comment is invisible to callers.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                yield parent_key, key
            yield from _iter_yaml_strings(value, parent_key=key if isinstance(key, str) else parent_key)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _iter_yaml_strings(item, parent_key=parent_key)
    elif isinstance(node, str):
        yield parent_key, node


def _strip_yaml_comments(text: str) -> str:
    """Drop YAML comments as a fallback when PyYAML is unavailable.

    Removes full-line comments and trailing `` #`` comments. This is an
    approximation (a `` #`` inside a quoted scalar is also cut), so it is
    only used when the real parser cannot be imported.
    """
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        match = re.search(r"\s+#", line)
        if match:
            line = line[: match.start()]
        kept.append(line)
    return "\n".join(kept)


class ProductionReadinessVerifier:
    """Verifies production readiness of RegEngine codebase."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.results: list[VerificationResult] = []

    def run_all_checks(self) -> bool:
        """Run all verification checks. Returns True if all pass."""
        print(f"{BOLD}{BLUE}RegEngine Production Readiness Verification{RESET}\n")
        print(f"Repository: {self.repo_root}\n")

        checks: list[Callable[[], VerificationResult]] = [
            self.check_texas_scraper_inheritance,
            self.check_correlation_middleware,
            self.check_rate_limit_security,
            self.check_railway_deployment_workflow,
            # docker-compose.prod.yml check removed — prod runs as a
            # consolidated Railway monolith built from the root Dockerfile,
            # not a docker-compose deploy. See CONSOLIDATION.md / #1429.
        ]

        for check in checks:
            result = check()
            self.results.append(result)
            print(result)
            print()

        # Print summary
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        print("=" * 70)
        print(f"{BOLD}Summary:{RESET}")
        print(f"  Passed: {GREEN}{passed}{RESET}/{total}")
        print(f"  Failed: {RED}{total - passed}{RESET}/{total}")

        if passed == total:
            print(f"\n{GREEN}{BOLD}✓ All production readiness checks passed!{RESET}")
            return True
        else:
            print(f"\n{RED}{BOLD}✗ Some checks failed. Review the output above.{RESET}")
            return False

    def check_texas_scraper_inheritance(self) -> VerificationResult:
        """Verify Texas scraper uses inheritance from GenericRSSScraper."""
        name = "Texas Scraper Inheritance"
        file_path = self.repo_root / "services/ingestion/app/scrapers/state_adaptors/tx_rss.py"

        if not file_path.exists():
            return VerificationResult(
                name,
                False,
                "Texas scraper file not found",
                f"Expected: {file_path}",
            )

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Parse the Python file
            tree = ast.parse(content)

            # Find the TexasRegistryScraper class
            scraper_class = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "TexasRegistryScraper":
                    scraper_class = node
                    break

            if not scraper_class:
                return VerificationResult(
                    name,
                    False,
                    "TexasRegistryScraper class not found",
                    "Expected class: TexasRegistryScraper",
                )

            # Check inheritance
            if not scraper_class.bases:
                return VerificationResult(
                    name,
                    False,
                    "TexasRegistryScraper does not inherit from any class",
                    "Expected: GenericRSSScraper",
                )

            base_name = scraper_class.bases[0]
            if isinstance(base_name, ast.Name) and base_name.id == "GenericRSSScraper":
                return VerificationResult(
                    name,
                    True,
                    "Texas scraper correctly inherits from GenericRSSScraper",
                    f"Location: {file_path.relative_to(self.repo_root)}",
                )
            else:
                return VerificationResult(
                    name,
                    False,
                    f"Texas scraper inherits from wrong class",
                    f"Expected: GenericRSSScraper, Found: {ast.unparse(base_name)}",
                )

        except Exception as e:
            return VerificationResult(
                name,
                False,
                f"Error parsing Texas scraper: {e}",
            )

    def check_correlation_middleware(self) -> VerificationResult:
        """Verify correlation ID middleware is implemented."""
        name = "Correlation ID Middleware"
        file_path = self.repo_root / "services/shared/observability/correlation.py"

        if not file_path.exists():
            return VerificationResult(
                name,
                False,
                "Correlation middleware file not found",
                f"Expected: {file_path}",
            )

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Structural check: each component must be defined in the code,
            # not merely mentioned in a comment or docstring.
            assigned, functions, methods, strings = _python_code_facts(content)

            missing = []
            if "correlation_id_ctx" not in assigned:
                missing.append("correlation_id_ctx (context variable assignment)")
            if "get_correlation_id" not in functions:
                missing.append("get_correlation_id (accessor function)")
            middleware_methods = methods.get("CorrelationIdMiddleware")
            if middleware_methods is None:
                missing.append("CorrelationIdMiddleware (middleware class)")
            elif "dispatch" not in middleware_methods:
                missing.append("CorrelationIdMiddleware.dispatch (request handler)")
            if "X-Correlation-ID" not in strings:
                missing.append("X-Correlation-ID (header string literal)")

            if missing:
                return VerificationResult(
                    name,
                    False,
                    "Missing required components",
                    f"Missing: {', '.join(missing)}",
                )

            return VerificationResult(
                name,
                True,
                "Correlation ID middleware fully implemented",
                f"Location: {file_path.relative_to(self.repo_root)}",
            )

        except Exception as e:
            return VerificationResult(
                name,
                False,
                f"Error reading correlation middleware: {e}",
            )

    def check_rate_limit_security(self) -> VerificationResult:
        """Verify brute-force rate limiting can use shared Redis counters."""
        name = "Rate Limiting Security (Shared Redis Counters)"
        file_path = self.repo_root / "services/shared/rate_limit.py"

        if not file_path.exists():
            return VerificationResult(
                name,
                False,
                "Rate limit file not found",
                f"Expected: {file_path}",
            )

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Structural check: the limiter class must exist with its key
            # methods, and each Redis env var must be an exact string literal
            # in the code. Mentions in comments or docstrings do not count.
            _assigned, _functions, methods, strings = _python_code_facts(content)

            missing = []
            limiter_methods = methods.get("BruteForceLimiter")
            if limiter_methods is None:
                missing.append("BruteForceLimiter (shared brute-force limiter class)")
            else:
                if "record_failure" not in limiter_methods:
                    missing.append("record_failure (failure counter mutation)")
                if "is_redis_backed" not in limiter_methods:
                    missing.append("is_redis_backed (shared-store status)")
            for env_var, description in [
                ("REGENGINE_REDIS_URL", "Primary Redis env var"),
                ("REDIS_URL", "Fallback Redis env var"),
            ]:
                if env_var not in strings:
                    missing.append(f"{env_var} ({description})")

            if not missing:
                return VerificationResult(
                    name,
                    True,
                    "Redis-backed brute-force limiter is implemented",
                    f"Location: {file_path.relative_to(self.repo_root)}",
                )
            else:
                return VerificationResult(
                    name,
                    False,
                    "Shared Redis counter implementation is incomplete",
                    f"Missing: {', '.join(missing)}",
                )

        except Exception as e:
            return VerificationResult(
                name,
                False,
                f"Error reading rate limit file: {e}",
            )

    def check_railway_deployment_workflow(self) -> VerificationResult:
        """Verify Railway deployment workflow is configured."""
        name = "Railway Deployment Workflow"
        file_path = self.repo_root / ".github/workflows/deploy.yml"

        if not file_path.exists():
            return VerificationResult(
                name,
                False,
                "Deployment workflow not found",
                f"Expected: {file_path}",
            )

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Structural check: the Railway CLI must be invoked from a run
            # step and each secret must be referenced by the workflow config.
            # Comment-only mentions do not count.
            secret_names = [
                "RAILWAY_API_TOKEN",
                "RAILWAY_PROJECT_ID",
                "RAILWAY_ENVIRONMENT_ID",
            ]
            if yaml is not None:
                try:
                    workflow = yaml.safe_load(content)
                except Exception:
                    return VerificationResult(
                        name,
                        False,
                        "Deployment workflow is not parseable as YAML",
                        f"Location: {file_path.relative_to(self.repo_root)}",
                    )
                if not isinstance(workflow, dict):
                    return VerificationResult(
                        name,
                        False,
                        "Deployment workflow has no YAML mapping at its root",
                        f"Location: {file_path.relative_to(self.repo_root)}",
                    )
                entries = list(_iter_yaml_strings(workflow))
                scalars = [text for _, text in entries]
                has_cli = any(
                    parent_key == "run" and re.search(r"railway\s+\S|@railway/", text, re.IGNORECASE)
                    for parent_key, text in entries
                )
                missing = [token for token in secret_names if not any(token in text for text in scalars)]
            else:
                code = _strip_yaml_comments(content).lower()
                has_cli = bool(re.search(r"railway\s+\S|@railway/", code))
                missing = [token for token in secret_names if token.lower() not in code]
            if not has_cli:
                missing.append("railway (CLI invocation in a run step)")
            if missing:
                return VerificationResult(
                    name,
                    False,
                    "Deployment workflow is missing required Railway configuration",
                    f"Missing: {', '.join(missing)}",
                )

            return VerificationResult(
                name,
                True,
                "Railway deployment workflow is configured",
                f"Location: {file_path.relative_to(self.repo_root)}",
            )

        except Exception as e:
            return VerificationResult(
                name,
                False,
                f"Error reading deployment workflow: {e}",
            )

    # check_docker_compose_prod removed — production no longer uses a
    # docker-compose.prod.yml. It's a consolidated Railway monolith built
    # from the root Dockerfile (see CONSOLIDATION.md, railway.toml,
    # server/main.py). Any future "is this deploy ready" check should run
    # against the root Dockerfile or the Railway API, not a compose file.


def main():
    """Main entry point."""
    # Find repository root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    if not (repo_root / ".git").exists():
        print(f"{RED}Error: Could not find repository root{RESET}")
        sys.exit(1)

    # Run verification
    verifier = ProductionReadinessVerifier(repo_root)
    success = verifier.run_all_checks()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
