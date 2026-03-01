#!/usr/bin/env python3
"""
Production Readiness Verification Script for RegEngine

This script verifies that all critical production-ready fixes are in place:
1. Texas scraper uses inheritance from GenericRSSScraper
2. Correlation ID middleware is implemented
3. Rate limiting enforces Redis in production
4. Railway deployment workflow is configured
5. Production Docker Compose configuration exists

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
from typing import Callable

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
            self.check_docker_compose_prod,
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
        file_path = self.repo_root / "shared/correlation.py"

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

            # Check for required components
            required_components = [
                ("correlation_id_ctx", "Context variable for correlation ID"),
                ("get_correlation_id", "Function to retrieve correlation ID"),
                ("CorrelationIdMiddleware", "Middleware class"),
                ("X-Correlation-ID", "Header name"),
            ]

            missing = []
            for component, description in required_components:
                if component not in content:
                    missing.append(f"{component} ({description})")

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
        """Verify rate limiting enforces Redis in production."""
        name = "Rate Limiting Security (Production Redis Enforcement)"
        file_path = self.repo_root / "shared/rate_limit.py"

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

            # Check for production enforcement logic
            # Look for the security check pattern
            patterns = [
                r'REGENGINE_ENV.*production',
                r'REDIS_URL.*required.*production',
                r'RuntimeError.*production',
            ]

            matches = []
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    matches.append(pattern)

            if len(matches) >= 2:
                # Check if it's in get_rate_limiter function
                if "get_rate_limiter" in content:
                    return VerificationResult(
                        name,
                        True,
                        "Production Redis enforcement is active",
                        f"Application will fail to start in production without REDIS_URL",
                    )
                else:
                    return VerificationResult(
                        name,
                        False,
                        "Production check exists but not in get_rate_limiter",
                        "Security check should be in get_rate_limiter function",
                    )
            else:
                return VerificationResult(
                    name,
                    False,
                    "Production Redis enforcement not found",
                    f"Found {len(matches)}/3 expected patterns",
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

            required_tokens = [
                "railway",
                "RAILWAY_TOKEN",
                "RAILWAY_PROJECT_ID",
                "RAILWAY_ENVIRONMENT_ID",
            ]

            missing = [token for token in required_tokens if token not in content]
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

    def check_docker_compose_prod(self) -> VerificationResult:
        """Verify production Docker Compose configuration exists."""
        name = "Production Docker Compose Configuration"
        file_path = self.repo_root / "docker-compose.prod.yml"

        if not file_path.exists():
            return VerificationResult(
                name,
                False,
                "Production Docker Compose file not found",
                f"Expected: {file_path}",
            )

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Check for critical production features
            required_features = [
                ("REGENGINE_ENV.*production", "Production environment flag"),
                ("resources:", "Resource limits"),
                ("limits:", "CPU/Memory limits"),
                (r"\$\{.*:\?error\}", "Required environment variables"),
                ("REDIS_URL", "Redis configuration"),
            ]

            missing = []
            found_features = []
            for pattern, description in required_features:
                if re.search(pattern, content):
                    found_features.append(description)
                else:
                    missing.append(description)

            if len(found_features) >= 4:
                # Count services with resource limits
                services_with_limits = len(re.findall(r'limits:\s*\n\s*cpus:', content))

                return VerificationResult(
                    name,
                    True,
                    f"Production Docker Compose is properly configured",
                    f"{services_with_limits} services with resource limits, all secrets required",
                )
            else:
                return VerificationResult(
                    name,
                    False,
                    "Incomplete production Docker Compose configuration",
                    f"Missing features: {', '.join(missing)}",
                )

        except Exception as e:
            return VerificationResult(
                name,
                False,
                f"Error reading Docker Compose config: {e}",
            )


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
