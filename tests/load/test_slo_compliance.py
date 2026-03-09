import logging
import os
from locust import HttpUser, task, between, events

# SLA Thresholds
TRACE_SLA_SEC = 2.0
EXPORT_SLA_SEC = 5.0
GAP_SLA_SEC = 1.0

class FSMALoadTest(HttpUser):
    wait_time = between(1, 5)
    
    def on_start(self):
        """Setup: Get a valid token if needed"""
        # In this environment, we might use a static admin key
        self.headers = {
            "X-RegEngine-API-Key": os.getenv("REGENGINE_TEST_API_KEY", "dev-admin-key"),
            "Content-Type": "application/json"
        }

    @task(10)
    def forward_trace(self):
        """High frequency: Trace forward simulation"""
        # User Spec: POST /v1/fsma/trace/forward with JSON
        with self.client.post(
            "/v1/fsma/trace/forward",
            json={"lot_code": "TEST-LOT-001"},
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() > 2.0: # p95 2s target
                    response.failure("p95 SLO breach")
            elif response.status_code != 404: 
                response.failure(f"Error: {response.status_code}")

    @task(3)
    def compliance_gaps(self):
        """Medium frequency: Compliance Dashboard load"""
        with self.client.get(
            "/v1/fsma/gaps",
            headers=self.headers,
            name="/gaps",
            catch_response=True
        ) as response:
            if response.elapsed.total_seconds() > GAP_SLA_SEC:
                response.failure(f"SLO Breach: > {GAP_SLA_SEC}s")

    @task(1)
    def export_trace_csv(self):
        """Low frequency: Heavy export operation"""
        tlc = "LOT-2025-ROMAINE-001"
        with self.client.get(
            f"/v1/fsma/export/trace/{tlc}",
            headers=self.headers,
            name="/export/trace",
            catch_response=True
        ) as response:
            if response.elapsed.total_seconds() > EXPORT_SLA_SEC:
                response.failure(f"SLO Breach: > {EXPORT_SLA_SEC}s")

@events.request.add_listener
def my_request_handler(request_type, name, response_time, response_length, exception, **kwargs):
    if exception:
        logging.error(f"Request to {name} failed with exception {exception}")
    if response_time > (TRACE_SLA_SEC * 1000):
        logging.warning(f"Slow request to {name}: {response_time}ms")
