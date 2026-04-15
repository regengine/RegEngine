from prometheus_client import Counter

regulatory_discovery_runs_total = Counter("regulatory_discovery_runs_total", "Total discovery runs")
regulatory_discovery_success = Counter("regulatory_discovery_success", "Successful discovery runs")
regulatory_discovery_failures = Counter("regulatory_discovery_failures", "Failed discovery runs")
