#!/usr/bin/env python3
"""
Chaos Engineering Automation Script for RegEngine.

This script implements automated chaos engineering tests to validate
system resilience and recovery mechanisms. It can:
- Kill/restart service containers
- Simulate Kafka broker failures
- Simulate database failures (PostgreSQL, Neo4j)
- Inject network latency/packet loss
- Validate recovery time objectives (RTO < 60s)
"""

import argparse
import docker
import time
import logging
import sys
import random
import requests
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

try:
    from sqlalchemy import create_engine, text
except ImportError:
    create_engine = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CANARY_TENANT_ID = "00000000-0000-0000-0000-000000000001"
CANARY_RECORD_UUID = os.getenv("CHAOS_CANARY_UUID", "Canary Record")


@dataclass
class ChaosTest:
    """Represents a single chaos engineering test."""
    name: str
    description: str
    target_container: str
    duration_seconds: int
    expected_rto: int = 60  # Recovery time objective in seconds


@dataclass
class ChaosResult:
    """Results from a chaos engineering test."""
    test_name: str
    success: bool
    downtime_seconds: float
    recovery_time_seconds: float
    rto_met: bool
    error_message: Optional[str] = None


class ChaosRunner:
    """Main chaos engineering runner."""

    def __init__(
        self,
        docker_client: docker.DockerClient,
        environment: str = "staging",
        rto_threshold: int = 60
    ):
        """
        Initialize chaos runner.

        Args:
            docker_client: Docker client instance
            environment: Target environment (staging/production)
            rto_threshold: Recovery time objective threshold in seconds
        """
        self.docker = docker_client
        self.environment = environment
        self.rto_threshold = rto_threshold
        self.results: List[ChaosResult] = []

    def run_test(self, test: ChaosTest) -> ChaosResult:
        """
        Execute a single chaos test.

        Args:
            test: ChaosTest to execute

        Returns:
            ChaosResult with test outcomes
        """
        logger.info(f"=" * 80)
        logger.info(f"Starting chaos test: {test.name}")
        logger.info(f"Description: {test.description}")
        logger.info(f"Target: {test.target_container}")
        logger.info(f"=" * 80)

        try:
            # Get target container
            container = self.docker.containers.get(test.target_container)

            # Record baseline health
            baseline_healthy = self._check_service_health(test.target_container)
            logger.info(f"Baseline health: {'✓ Healthy' if baseline_healthy else '✗ Unhealthy'}")

            # Capture baseline data counts BEFORE chaos event
            if os.getenv("CHAOS_SEED_MANIFEST"):
                logger.info(f"📊 Loading baseline data counts from manifest")
                with open(os.getenv("CHAOS_SEED_MANIFEST")) as f:
                    baseline_counts = json.load(f)
                logger.info(f"✅ Loaded baseline: {baseline_counts}")
            else:
                logger.info("📊 Capturing baseline data counts...")
                baseline_counts = self._capture_data_counts()

            # Execute chaos action
            start_time = time.time()
            logger.warning(f"⚡ Killing container: {test.target_container}")
            container.kill()

            # Wait for specified duration
            logger.info(f"⏳ Waiting {test.duration_seconds}s for system to detect failure...")
            time.sleep(test.duration_seconds)

            # Restart container
            logger.info(f"🔄 Restarting container: {test.target_container}")
            container.restart()

            # Wait for recovery and measure RTO
            recovery_start = time.time()
            recovered = self._wait_for_recovery(
                test.target_container,
                timeout=self.rto_threshold
            )
            recovery_time = time.time() - recovery_start
            total_downtime = time.time() - start_time

            # Validate data integrity with baseline comparison
            data_integrity_ok = self._validate_data_integrity(baseline_counts)

            # Determine success
            success = (
                recovered
                and recovery_time <= self.rto_threshold
                and data_integrity_ok
            )

            result = ChaosResult(
                test_name=test.name,
                success=success,
                downtime_seconds=total_downtime,
                recovery_time_seconds=recovery_time,
                rto_met=recovery_time <= self.rto_threshold
            )

            # Log results
            logger.info(f"\n{'='*80}")
            logger.info(f"Test Results: {test.name}")
            logger.info(f"Status: {'✅ PASSED' if success else '❌ FAILED'}")
            logger.info(f"Total Downtime: {total_downtime:.2f}s")
            logger.info(f"Recovery Time: {recovery_time:.2f}s (RTO: {self.rto_threshold}s)")
            logger.info(f"RTO Met: {'✅' if result.rto_met else '❌'}")
            logger.info(f"Data Integrity: {'✅' if data_integrity_ok else '❌'}")
            logger.info(f"{'='*80}\n")

            return result

        except Exception as e:
            logger.error(f"Chaos test failed with exception: {e}", exc_info=True)
            return ChaosResult(
                test_name=test.name,
                success=False,
                downtime_seconds=0,
                recovery_time_seconds=0,
                rto_met=False,
                error_message=str(e)
            )

    def _check_service_health(self, container_name: str) -> bool:
        """
        Check if a service container is healthy.

        Args:
            container_name: Name of the container

        Returns:
            True if healthy, False otherwise
        """
        try:
            container = self.docker.containers.get(container_name)

            # Check container status
            container.reload()
            if container.status != "running":
                return False

            # Check health check if available
            health = container.attrs.get("State", {}).get("Health", {})
            if health:
                return health.get("Status") == "healthy"

            # Fallback: check if container is running
            return True

        except Exception as e:
            logger.warning(f"Failed to check health for {container_name}: {e}")
            return False

    def _wait_for_recovery(
        self,
        container_name: str,
        timeout: int = 60,
        check_interval: int = 2
    ) -> bool:
        """
        Wait for a service to recover after failure.

        Args:
            container_name: Name of the container
            timeout: Maximum time to wait in seconds
            check_interval: Seconds between health checks

        Returns:
            True if recovered within timeout, False otherwise
        """
        start_time = time.time()
        attempts = 0

        while time.time() - start_time < timeout:
            attempts += 1
            elapsed = time.time() - start_time

            if self._check_service_health(container_name):
                logger.info(
                    f"✅ Service recovered after {elapsed:.2f}s "
                    f"({attempts} health check attempts)"
                )
                return True

            logger.debug(
                f"⏳ Waiting for recovery... "
                f"({elapsed:.1f}s/{timeout}s, attempt {attempts})"
            )
            time.sleep(check_interval)

        logger.error(f"❌ Service did not recover within {timeout}s timeout")
        return False

    def _capture_data_counts(self) -> Dict[str, int]:
        """
        Capture current data counts from all databases.

        Returns:
            Dictionary with database counts (neo4j_nodes, neo4j_relationships, postgres_rows)
        """
        counts = {
            "neo4j_nodes": 0,
            "neo4j_relationships": 0,
            "postgres_api_keys": 0
        }

        # Count Neo4j nodes and relationships
        if GraphDatabase:
            try:
                uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
                user = os.getenv("NEO4J_USER", "neo4j")
                password = os.getenv("NEO4J_PASSWORD", "test-password")

                # Handle docker service name in URI if running locally
                if "neo4j:" in uri:
                    uri = uri.replace("neo4j:", "localhost:")

                with GraphDatabase.driver(uri, auth=(user, password)) as driver:
                    driver.verify_connectivity()
                    with driver.session() as session:
                        # Count nodes
                        result = session.run("MATCH (n) RETURN count(n) as count")
                        counts["neo4j_nodes"] = result.single()["count"]

                        # Count relationships
                        result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                        counts["neo4j_relationships"] = result.single()["count"]

                logger.info(f"📊 Neo4j counts: {counts['neo4j_nodes']} nodes, {counts['neo4j_relationships']} relationships")
            except Exception as e:
                logger.warning(f"⚠️ Could not capture Neo4j counts: {e}")
        else:
            logger.warning("⚠️ Neo4j driver not installed, skipping Neo4j counts")

        # Count PostgreSQL rows in key tables
        if create_engine:
            try:
                db_url = os.getenv("ADMIN_DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine_admin")
                # Handle docker service name
                if "@postgres:" in db_url:
                    db_url = db_url.replace("@postgres:", "@localhost:")

                engine = create_engine(db_url)
                with engine.connect() as conn:
                    # Count API keys
                    result = conn.execute(text("SELECT COUNT(*) FROM api_keys WHERE enabled = true"))
                    counts["postgres_api_keys"] = result.scalar() or 0

                logger.info(f"📊 PostgreSQL counts: {counts['postgres_api_keys']} API keys")
            except Exception as e:
                logger.warning(f"⚠️ Could not capture PostgreSQL counts: {e}")
        else:
            logger.warning("⚠️ SQLAlchemy not installed, skipping PostgreSQL counts")

        return counts

    def _validate_data_integrity(self, baseline_counts: Optional[Dict[str, int]] = None) -> bool:
        """
        Validate data integrity after chaos event by comparing current counts with baseline.

        Args:
            baseline_counts: Baseline counts captured before chaos event

        Returns:
            True if data integrity is maintained (counts match baseline), False otherwise
        """
        logger.info("🔍 Validating data integrity...")

        if GraphDatabase:
            try:
                uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
                user = os.getenv("NEO4J_USER", "neo4j")
                password = os.getenv("NEO4J_PASSWORD", "test-password")

                if "neo4j:" in uri:
                    uri = uri.replace("neo4j:", "localhost:")

                with GraphDatabase.driver(uri, auth=(user, password)) as driver:
                    with driver.session() as session:
                        result = session.run(
                            """
                            MATCH (p:Provision)
                            WHERE p.pid = $canary_id OR p.id = $canary_id
                            RETURN p.pid AS pid
                            """,
                            canary_id=CANARY_RECORD_UUID,
                        ).single()
                        if result is None:
                            logger.critical(
                                "CRITICAL: Canary record missing after chaos event",
                                canary_id=CANARY_RECORD_UUID,
                                tenant_id=CANARY_TENANT_ID,
                            )
                            return False
                        logger.info(
                            "✅ Canary record present",
                            canary_id=CANARY_RECORD_UUID,
                            tenant_id=CANARY_TENANT_ID,
                        )
            except Exception as e:
                logger.error(f"❌ Canary validation failed: {e}")
                return False

        # If no baseline provided, just check connectivity
        if baseline_counts is None:
            logger.warning("⚠️ No baseline counts provided, performing basic connectivity check only")
            integrity_ok = True

            # Check Neo4j connectivity
            if GraphDatabase:
                try:
                    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
                    user = os.getenv("NEO4J_USER", "neo4j")
                    password = os.getenv("NEO4J_PASSWORD", "test-password")

                    if "neo4j:" in uri:
                        uri = uri.replace("neo4j:", "localhost:")

                    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
                        driver.verify_connectivity()
                    logger.info("✅ Neo4j connectivity check passed")
                except Exception as e:
                    logger.error(f"❌ Neo4j connectivity check failed: {e}")
                    integrity_ok = False

            # Check PostgreSQL connectivity
            if create_engine:
                try:
                    db_url = os.getenv("ADMIN_DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine_admin")
                    if "@postgres:" in db_url:
                        db_url = db_url.replace("@postgres:", "@localhost:")

                    engine = create_engine(db_url)
                    with engine.connect() as conn:
                        conn.execute(text("SELECT 1"))
                    logger.info("✅ PostgreSQL connectivity check passed")
                except Exception as e:
                    logger.error(f"❌ PostgreSQL connectivity check failed: {e}")
                    integrity_ok = False

            return integrity_ok

        # Compare current counts with baseline
        current_counts = self._capture_data_counts()
        integrity_ok = True

        logger.info("📊 Comparing data counts (baseline vs current):")

        for key, baseline_value in baseline_counts.items():
            current_value = current_counts.get(key, 0)
            match = baseline_value == current_value
            status = "✅" if match else "❌"

            logger.info(f"  {status} {key}: {baseline_value} -> {current_value}")

            if not match:
                integrity_ok = False
                logger.error(f"  ❌ Data loss detected in {key}: {baseline_value - current_value} items lost")

        if integrity_ok:
            logger.info("✅ Data integrity validation PASSED - no data loss detected")
        else:
            logger.error("❌ Data integrity validation FAILED - data loss detected")

        return integrity_ok

    def run_kafka_broker_failure(self, duration_seconds: int = 30) -> ChaosResult:
        """
        Simulate Kafka/Redpanda broker failure.

        Args:
            duration_seconds: How long to keep broker down

        Returns:
            ChaosResult
        """
        test = ChaosTest(
            name="Kafka Broker Failure",
            description="Simulate Kafka broker failure and validate consumer recovery",
            target_container="regengine-redpanda-1",
            duration_seconds=duration_seconds
        )
        return self.run_test(test)

    def run_neo4j_failure(self, duration_seconds: int = 20) -> ChaosResult:
        """
        Simulate Neo4j database failure.

        Args:
            duration_seconds: How long to keep database down

        Returns:
            ChaosResult
        """
        test = ChaosTest(
            name="Neo4j Database Failure",
            description="Simulate Neo4j failure and validate graph service recovery",
            target_container="regengine-neo4j-1",
            duration_seconds=duration_seconds
        )
        return self.run_test(test)

    def run_postgres_failure(self, duration_seconds: int = 20) -> ChaosResult:
        """
        Simulate PostgreSQL database failure.

        Args:
            duration_seconds: How long to keep database down

        Returns:
            ChaosResult
        """
        test = ChaosTest(
            name="PostgreSQL Database Failure",
            description="Simulate PostgreSQL failure and validate admin service recovery",
            target_container="regengine-postgres-1",
            duration_seconds=duration_seconds
        )
        return self.run_test(test)

    def run_service_failure(
        self,
        service_name: str,
        duration_seconds: int = 15
    ) -> ChaosResult:
        """
        Simulate microservice failure.

        Args:
            service_name: Name of the service (admin, ingestion, nlp, graph, opportunity)
            duration_seconds: How long to keep service down

        Returns:
            ChaosResult
        """
        container_name = f"regengine-{service_name}-1"
        test = ChaosTest(
            name=f"{service_name.title()} Service Failure",
            description=f"Simulate {service_name} service crash and validate auto-recovery",
            target_container=container_name,
            duration_seconds=duration_seconds
        )
        return self.run_test(test)

    def run_all_tests(self) -> List[ChaosResult]:
        """
        Run comprehensive chaos engineering test suite.

        Returns:
            List of ChaosResults
        """
        logger.info("🚀 Starting comprehensive chaos engineering test suite")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"RTO Threshold: {self.rto_threshold}s\n")

        self.results = []

        # Test 1: Neo4j failure
        logger.info("\n📊 Test 1/6: Neo4j Database Failure")
        self.results.append(self.run_neo4j_failure(duration_seconds=20))
        time.sleep(10)  # Cooldown between tests

        # Test 2: Kafka broker failure
        logger.info("\n📊 Test 2/6: Kafka Broker Failure")
        self.results.append(self.run_kafka_broker_failure(duration_seconds=30))
        time.sleep(10)

        # Test 3: Graph service failure
        logger.info("\n📊 Test 3/6: Graph Service Failure")
        self.results.append(self.run_service_failure("graph-service", duration_seconds=15))
        time.sleep(10)

        # Test 4: NLP service failure
        logger.info("\n📊 Test 4/6: NLP Service Failure")
        self.results.append(self.run_service_failure("nlp-service", duration_seconds=15))
        time.sleep(10)

        # Test 5: Ingestion service failure
        logger.info("\n📊 Test 5/6: Ingestion Service Failure")
        self.results.append(self.run_service_failure("ingestion-service", duration_seconds=15))
        time.sleep(10)

        # Test 6: Admin API failure
        logger.info("\n📊 Test 6/6: Admin API Failure")
        self.results.append(self.run_service_failure("admin-api", duration_seconds=15))

        # Print summary
        self._print_summary()

        return self.results

    def _print_summary(self):
        """Print test summary."""
        logger.info("\n" + "=" * 80)
        logger.info("CHAOS ENGINEERING TEST SUMMARY")
        logger.info("=" * 80)

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests
        rto_met_count = sum(1 for r in self.results if r.rto_met)

        logger.info(f"\nTotal Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests} ✅")
        logger.info(f"Failed: {failed_tests} ❌")
        logger.info(f"RTO Met: {rto_met_count}/{total_tests}\n")

        logger.info("Individual Test Results:")
        logger.info("-" * 80)
        for result in self.results:
            status = "✅ PASS" if result.success else "❌ FAIL"
            rto_status = "✅" if result.rto_met else "❌"
            logger.info(
                f"{result.test_name:40s} | {status} | "
                f"Recovery: {result.recovery_time_seconds:5.2f}s {rto_status}"
            )

        logger.info("=" * 80)

        # Exit code based on results
        if failed_tests > 0:
            sys.exit(1)
        else:
            sys.exit(0)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="RegEngine Chaos Engineering Test Runner"
    )
    parser.add_argument(
        "--environment",
        choices=["staging", "production"],
        default="staging",
        help="Target environment (default: staging)"
    )
    parser.add_argument(
        "--rto",
        type=int,
        default=60,
        help="Recovery time objective in seconds (default: 60)"
    )
    parser.add_argument(
        "--test",
        choices=["neo4j", "kafka", "postgres", "graph", "nlp", "ingestion", "admin", "all"],
        default="all",
        help="Specific test to run (default: all)"
    )

    args = parser.parse_args()

    # Initialize Docker client
    try:
        client = docker.from_env()
        logger.info("✅ Connected to Docker daemon")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Docker: {e}")
        sys.exit(1)

    # Create chaos runner
    runner = ChaosRunner(
        docker_client=client,
        environment=args.environment,
        rto_threshold=args.rto
    )

    # Run tests
    if args.test == "all":
        runner.run_all_tests()
    elif args.test == "neo4j":
        result = runner.run_neo4j_failure()
        sys.exit(0 if result.success else 1)
    elif args.test == "kafka":
        result = runner.run_kafka_broker_failure()
        sys.exit(0 if result.success else 1)
    elif args.test == "postgres":
        result = runner.run_postgres_failure()
        sys.exit(0 if result.success else 1)
    else:
        result = runner.run_service_failure(args.test)
        sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
