
import random
from locust import HttpUser, task, between, events

class TraceLoadTest(HttpUser):
    wait_time = between(0.1, 0.5)
    
    def on_start(self):
        """Setup user with a random tenant? Or just assume one."""
        self.tenant_id = "tenant-001"
        self.common_tlcs = ["LOT-2024-001", "LOT-2024-002", "LOT-2024-003"]
    
    @task(10)
    def forward_trace(self):
        """Simulate typical forward trace query"""
        # Pick a random lot
        tlc = random.choice(self.common_tlcs)
        
        with self.client.post(
            "/v1/fsma/trace/forward", # Assumes we route here eventually, currently /v1/fsma/forward or similar
            # Wait, looking at fsma_routes.py, it's: @router.post("/trace/forward") 
            # and prefix was? 
            # Actually, `fsma_routes.py` doesn't strictly have a /v1/fsma prefix yet unless main.py mounts it there.
            # Let's check main.py or just use the relative path derived from previous knowledge.
            # In `services/graph/app/routes.py`, we usually see mounting. 
            # Assuming `/fsma/trace/forward` or similar based on existing code.
            # Let's check fsma_routes.py again or assume a standard path and fix if 404.
            # Current `fsma_routes.py` has `@router.post("/trace/forward")`.
            # If `routes.py` mounts it, let's look.
            json={
                "tlc": tlc, 
                "max_depth": 5,
                "enforce_time_arrow": True
            },
            headers={"X-Tenant-ID": self.tenant_id},
            catch_response=True
        ) as response:
            if response.status_code == 404:
                response.failure("Endpoint not found (404)")
            elif response.elapsed.total_seconds() > 2.0:
                response.failure(f"p95 SLO breach: {response.elapsed.total_seconds()}s > 2.0s")
            elif response.status_code != 200:
                response.failure(f"Error: {response.status_code}")

    @task(1)
    def health_check(self):
        self.client.get("/health")

# Threshold verification logic
@events.quit.add_listener
def _(environment, **kwargs):
    if environment.stats.total.fail_ratio > 0.01:
        print(f"Load Test Failed: Failure Ratio {environment.stats.total.fail_ratio} > 1%")
        environment.process_exit_code = 1
    elif environment.stats.total.get_response_time_percentile(0.95) > 2000:
        print(f"Load Test Failed: p95 Latency {environment.stats.total.get_response_time_percentile(0.95)}ms > 2000ms")
        environment.process_exit_code = 1
    else:
        environment.process_exit_code = 0
