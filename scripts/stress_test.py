#!/usr/bin/env python3
"""
RegEngine Massive Stress Test
Tests all 6 services: ingestion, NLP, graph, admin, compliance, scheduler
Covers: health, read endpoints, write endpoints, concurrent load, error handling
"""

import asyncio
import aiohttp
import json
import time
import sys
import statistics
from dataclasses import dataclass, field
from typing import Optional

# ─── CONFIG ───
CONCURRENCY = 50          # simultaneous connections
REQUESTS_PER_ENDPOINT = 100  # requests per test
TIMEOUT = 10              # seconds per request

TEST_TENANT = "00000000-0000-0000-0000-000000000123"
ADMIN_KEY = "8f623912638891629831b9d8c91c9182dec283746571928374abcdef123456"

SERVICES = {
    "ingestion":  "http://localhost:8002",
    "nlp":        "http://localhost:8100",
    "graph":      "http://localhost:8200",
    "admin":      "http://localhost:8400",
    "compliance": "http://localhost:8500",
    "scheduler":  "http://localhost:8600",
}

@dataclass
class EndpointResult:
    name: str
    method: str
    url: str
    total_requests: int = 0
    success: int = 0
    errors: int = 0
    latencies: list = field(default_factory=list)
    status_codes: dict = field(default_factory=dict)
    error_messages: list = field(default_factory=list)

    @property
    def p50(self):
        return statistics.median(self.latencies) if self.latencies else 0

    @property
    def p95(self):
        if not self.latencies:
            return 0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def p99(self):
        if not self.latencies:
            return 0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * 0.99)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def avg(self):
        return statistics.mean(self.latencies) if self.latencies else 0

    @property
    def rps(self):
        total_time = sum(self.latencies) if self.latencies else 1
        return len(self.latencies) / max(total_time, 0.001)


# ─── TEST DEFINITIONS ───

TESTS = [
    # === HEALTH CHECKS (all 6 services) ===
    {"name": "ingestion/health",  "method": "GET",  "url": "{ingestion}/health"},
    {"name": "nlp/health",        "method": "GET",  "url": "{nlp}/health"},
    {"name": "graph/health",      "method": "GET",  "url": "{graph}/health"},
    {"name": "admin/health",      "method": "GET",  "url": "{admin}/health"},
    {"name": "compliance/health", "method": "GET",  "url": "{compliance}/health"},
    {"name": "scheduler/health",  "method": "GET",  "url": "{scheduler}/health"},

    # === READINESS PROBES ===
    {"name": "ingestion/ready",  "method": "GET",  "url": "{ingestion}/ready"},
    {"name": "nlp/ready",        "method": "GET",  "url": "{nlp}/ready"},
    {"name": "graph/ready",      "method": "GET",  "url": "{graph}/ready"},
    {"name": "admin/ready",      "method": "GET",  "url": "{admin}/ready"},

    # === INGESTION SERVICE ===
    {"name": "ingestion/templates",      "method": "GET",  "url": "{ingestion}/api/v1/templates"},
    {"name": "ingestion/ftl-categories", "method": "GET",  "url": "{ingestion}/api/v1/products/categories/ftl"},
    {"name": "ingestion/export-formats", "method": "GET",  "url": "{ingestion}/api/v1/export/formats"},
    {"name": "ingestion/billing-plans",  "method": "GET",  "url": "{ingestion}/api/v1/billing/plans"},
    {"name": "ingestion/onboard-steps",  "method": "GET",  "url": "{ingestion}/api/v1/onboarding/steps"},
    {"name": "ingestion/sim-scenarios",  "method": "GET",  "url": "{ingestion}/api/v1/simulations/scenarios"},
    {"name": "ingestion/integrations",   "method": "GET",  "url": "{ingestion}/api/v1/integrations/available"},
    {"name": "ingestion/team-roles",     "method": "GET",  "url": "{ingestion}/api/v1/team/roles/definitions"},
    {"name": "ingestion/epcis-validate", "method": "POST", "url": "{ingestion}/api/v1/epcis/validate",
     "body": {
         "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
         "type": "ObjectEvent",
         "eventTime": "2026-02-28T09:30:00.000-05:00",
         "eventTimeZoneOffset": "-05:00",
         "action": "OBSERVE",
         "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
         "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
         "ilmd": {"cbvmda:lotNumber": "ROM-0042", "fsma:traceabilityLotCode": "00012345678901-ROM0042"}
     }},

    # === GRAPH SERVICE ===
    {"name": "graph/regulations",     "method": "GET",  "url": "{graph}/api/v1/regulations/list"},
    {"name": "graph/reg-mappings",    "method": "GET",  "url": "{graph}/api/v1/regulations/mappings"},
    {"name": "graph/recall-history",  "method": "GET",  "url": "{graph}/api/v1/fsma/recall/history"},
    {"name": "graph/recall-readiness","method": "GET",  "url": "{graph}/api/v1/fsma/recall/readiness"},
    {"name": "graph/recall-sla",      "method": "GET",  "url": "{graph}/api/v1/fsma/recall/sla"},
    {"name": "graph/compliance-coverage", "method": "GET", "url": "{graph}/api/v1/fsma/compliance/coverage"},
    {"name": "graph/compliance-gaps", "method": "GET",  "url": "{graph}/api/v1/fsma/compliance/gaps"},
    {"name": "graph/compliance-score","method": "GET",  "url": "{graph}/api/v1/fsma/compliance/score"},
    {"name": "graph/metrics",         "method": "GET",  "url": "{graph}/api/v1/fsma/metrics/metrics"},
    {"name": "graph/dashboard",       "method": "GET",  "url": "{graph}/api/v1/fsma/metrics/dashboard"},
    {"name": "graph/search-events",   "method": "GET",  "url": "{graph}/api/v1/fsma/traceability/search/events"},
    {"name": "graph/reg-search",      "method": "GET",  "url": "{graph}/api/v1/regulations/search?q=fsma"},

    # === ADMIN SERVICE ===
    {"name": "admin/system-status",   "method": "GET",  "url": "{admin}/v1/system/status"},
    {"name": "admin/system-metrics",  "method": "GET",  "url": "{admin}/v1/system/metrics"},
    {"name": "admin/ftl-categories",  "method": "GET",  "url": "{admin}/v1/supplier/ftl-categories"},
    {"name": "admin/social-proof",    "method": "GET",  "url": "{admin}/v1/supplier/social-proof"},
    {"name": "admin/admin-roles",     "method": "GET",  "url": "{admin}/v1/admin/roles"},

    # === COMPLIANCE SERVICE ===
    {"name": "compliance/risk-summary", "method": "GET", "url": "{compliance}/v1/risk/summary"},
    {"name": "compliance/ckg-summary",  "method": "GET", "url": "{compliance}/v1/ckg/summary"},
    {"name": "compliance/scope-wall",   "method": "GET", "url": "{compliance}/v1/scope-wall"},

    # === NLP SERVICE ===
    {"name": "nlp/metrics", "method": "GET", "url": "{nlp}/api/v1/metrics"},
    {"name": "nlp/query",   "method": "POST", "url": "{nlp}/api/v1/query/traceability",
     "body": {"query": "What are the FSMA 204 requirements for leafy greens?"}},

    # === ERROR HANDLING (intentional bad requests) ===
    {"name": "ingestion/404",        "method": "GET",  "url": "{ingestion}/api/v1/nonexistent", "expect_error": True},
    {"name": "admin/bad-tenant",     "method": "GET",  "url": "{admin}/v1/compliance/status/not-a-uuid", "expect_error": True},
    {"name": "graph/bad-tlc-trace",  "method": "GET",  "url": "{graph}/api/v1/fsma/traceability/trace/forward/INVALID", "expect_error": True},
    {"name": "ingestion/empty-epcis","method": "POST", "url": "{ingestion}/api/v1/epcis/validate",
     "body": {}, "expect_error": True},
]


async def run_single_request(session: aiohttp.ClientSession, test: dict, result: EndpointResult):
    """Execute a single HTTP request and record metrics."""
    url = test["url"]
    for svc, base in SERVICES.items():
        url = url.replace(f"{{{svc}}}", base)

    headers = {"Content-Type": "application/json"}
    body = test.get("body")

    start = time.monotonic()
    try:
        if test["method"] == "GET":
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                status = resp.status
                await resp.read()
        else:
            async with session.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                status = resp.status
                await resp.read()

        elapsed = time.monotonic() - start
        result.latencies.append(elapsed)
        result.total_requests += 1
        result.status_codes[status] = result.status_codes.get(status, 0) + 1

        if test.get("expect_error"):
            if status >= 400:
                result.success += 1
            else:
                result.errors += 1
                result.error_messages.append(f"Expected error but got {status}")
        else:
            if status < 400:
                result.success += 1
            else:
                result.errors += 1
                result.error_messages.append(f"HTTP {status}")

    except Exception as e:
        elapsed = time.monotonic() - start
        result.latencies.append(elapsed)
        result.total_requests += 1
        result.errors += 1
        result.error_messages.append(str(e)[:80])


async def run_endpoint_test(test: dict, count: int, concurrency: int) -> EndpointResult:
    """Run concurrent load against a single endpoint."""
    result = EndpointResult(
        name=test["name"],
        method=test["method"],
        url=test["url"],
    )

    connector = aiohttp.TCPConnector(limit=concurrency, force_close=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        sem = asyncio.Semaphore(concurrency)

        async def bounded_request():
            async with sem:
                await run_single_request(session, test, result)

        tasks = [bounded_request() for _ in range(count)]
        await asyncio.gather(*tasks)

    return result


def print_results(results: list[EndpointResult]):
    """Print formatted stress test results."""
    print("\n" + "=" * 100)
    print("  REGENGINE STRESS TEST RESULTS")
    print("=" * 100)
    print(f"  Concurrency: {CONCURRENCY}  |  Requests/endpoint: {REQUESTS_PER_ENDPOINT}  |  Timeout: {TIMEOUT}s")
    print("=" * 100)

    total_requests = 0
    total_success = 0
    total_errors = 0
    all_latencies = []
    failed_endpoints = []

    # Group by service
    services = {}
    for r in results:
        svc = r.name.split("/")[0]
        if svc not in services:
            services[svc] = []
        services[svc].append(r)

    for svc_name, svc_results in services.items():
        print(f"\n  ┌─ {svc_name.upper()} SERVICE {'─' * (80 - len(svc_name))}")

        for r in svc_results:
            total_requests += r.total_requests
            total_success += r.success
            total_errors += r.errors
            all_latencies.extend(r.latencies)

            status = "✅" if r.errors == 0 else "❌"
            endpoint_name = r.name.split("/", 1)[1] if "/" in r.name else r.name

            codes_str = " ".join(f"{k}:{v}" for k, v in sorted(r.status_codes.items()))

            print(f"  │ {status} {endpoint_name:<30} "
                  f"{r.success:>4}/{r.total_requests:<4} "
                  f"p50={r.p50*1000:>6.1f}ms  "
                  f"p95={r.p95*1000:>6.1f}ms  "
                  f"p99={r.p99*1000:>6.1f}ms  "
                  f"[{codes_str}]")

            if r.errors > 0:
                failed_endpoints.append(r)
                unique_errors = list(set(r.error_messages[:3]))
                for err in unique_errors:
                    print(f"  │   ↳ {err}")

        print(f"  └{'─' * 95}")

    # Summary
    print(f"\n{'=' * 100}")
    print(f"  SUMMARY")
    print(f"{'=' * 100}")
    print(f"  Total requests:   {total_requests:,}")
    print(f"  Successful:       {total_success:,} ({total_success/max(total_requests,1)*100:.1f}%)")
    print(f"  Errors:           {total_errors:,} ({total_errors/max(total_requests,1)*100:.1f}%)")

    if all_latencies:
        sorted_all = sorted(all_latencies)
        print(f"  Avg latency:      {statistics.mean(all_latencies)*1000:.1f}ms")
        print(f"  p50 latency:      {statistics.median(all_latencies)*1000:.1f}ms")
        p95_idx = int(len(sorted_all) * 0.95)
        print(f"  p95 latency:      {sorted_all[min(p95_idx, len(sorted_all)-1)]*1000:.1f}ms")
        p99_idx = int(len(sorted_all) * 0.99)
        print(f"  p99 latency:      {sorted_all[min(p99_idx, len(sorted_all)-1)]*1000:.1f}ms")
        print(f"  Max latency:      {max(all_latencies)*1000:.1f}ms")
        total_wall = sum(all_latencies)
        print(f"  Throughput:       ~{total_requests / max(total_wall/CONCURRENCY, 0.001):.0f} req/s effective")

    if failed_endpoints:
        print(f"\n  ⚠️  {len(failed_endpoints)} endpoint(s) had failures:")
        for r in failed_endpoints:
            print(f"     - {r.name}: {r.errors} errors / {r.total_requests} total")
    else:
        print(f"\n  ✅ ALL ENDPOINTS PASSED")

    print(f"{'=' * 100}\n")

    return total_errors == 0


async def main():
    print(f"\n🔥 Starting RegEngine Stress Test")
    print(f"   {len(TESTS)} endpoints × {REQUESTS_PER_ENDPOINT} requests = {len(TESTS) * REQUESTS_PER_ENDPOINT:,} total requests")
    print(f"   Concurrency: {CONCURRENCY}\n")

    results = []
    for i, test in enumerate(TESTS):
        endpoint_label = test["name"]
        progress = f"[{i+1}/{len(TESTS)}]"
        sys.stdout.write(f"  {progress} Testing {endpoint_label:<40}")
        sys.stdout.flush()

        start = time.monotonic()
        result = await run_endpoint_test(test, REQUESTS_PER_ENDPOINT, CONCURRENCY)
        elapsed = time.monotonic() - start

        status = "✅" if result.errors == 0 else "❌"
        sys.stdout.write(f" {status}  {elapsed:.1f}s  (p50={result.p50*1000:.0f}ms)\n")
        results.append(result)

    success = print_results(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
