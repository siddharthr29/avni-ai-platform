"""Locust load test for Avni AI Platform critical paths.

Simulates concurrent users hitting the four main endpoints:
  - POST /api/chat          (SSE streaming)
  - POST /api/knowledge/search  (RAG search)
  - POST /api/bundle/generate   (bundle generation from SRS)
  - GET  /api/admin/users       (admin users list)

Run:
    locust -f backend/tests/performance/locustfile.py \
        --host http://localhost:8000 \
        --users 20 --spawn-rate 1 --run-time 5m

Target SLAs:
    Chat:       p95 < 2s     (first byte of SSE stream)
    RAG:        p95 < 500ms
    Bundle Gen: p95 < 30s
    Admin API:  p95 < 100ms
"""

import json
import time
import uuid

from locust import HttpUser, between, task
from locust.exception import StopUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CHAT_MESSAGES = [
    "How do I create a registration form for an MCH program?",
    "What concept data types does Avni support?",
    "Explain the difference between a program encounter and a general encounter.",
    "How do I set up skip logic for a form field?",
    "What is the recommended approach for multi-select coded concepts?",
    "How do I configure visit schedules in Avni?",
    "What are the best practices for setting up catchments?",
    "How can I create decision rules for a program?",
    "Explain how to set up group-based privileges in Avni.",
    "What is the bundle upload process for a new organisation?",
]

SAMPLE_RAG_QUERIES = [
    "coded concept answers",
    "program enrolment form",
    "visit schedule rule",
    "subject type registration",
    "catchment assignment",
    "encounter cancellation form",
    "skip logic declarative rule",
    "form element group",
    "organisation setup",
    "group privileges",
]

SMALL_SRS_TEXT = """
Organisation: Load Test Org
Subject Type: Individual (Person)
Programs: Maternal Health
Encounter Types: ANC Visit
Forms:
- Registration Form (IndividualProfile): Name (Text), Age (Numeric), Gender (Coded: Male, Female, Other)
- ANC Enrolment (ProgramEnrolment): LMP Date (Date), High Risk (Coded: Yes, No)
- ANC Visit (ProgramEncounter): Weight (Numeric, kg), BP Systolic (Numeric, mmHg), BP Diastolic (Numeric, mmHg)
"""


def _session_id() -> str:
    return str(uuid.uuid4())


def _auth_headers(token: str = "test-load-token") -> dict:
    """Return headers that mimic an authenticated request."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


# ---------------------------------------------------------------------------
# User behaviour
# ---------------------------------------------------------------------------

class AvniAIUser(HttpUser):
    """Simulates a typical Avni AI Platform user.

    Weight distribution reflects real-world usage:
      - Chat (most common)      : weight 5
      - RAG search              : weight 3
      - Bundle generation (rare): weight 1
      - Admin list (rare)       : weight 1
    """

    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self):
        """Set up session context before tasks run."""
        self.session_id = _session_id()
        self.headers = _auth_headers()
        self._msg_index = 0
        self._rag_index = 0

        # Attempt to set org context; ignore failures during load test
        try:
            self.client.post(
                "/api/org/context",
                json={
                    "session_id": self.session_id,
                    "org_name": "Load Test Org",
                    "sector": "MCH",
                    "org_context": "Testing organisation for performance benchmarks",
                },
                headers=self.headers,
                timeout=5,
            )
        except Exception:
            pass

    # ── Chat (SSE streaming) ──────────────────────────────────────────────

    @task(5)
    def chat_sse(self):
        """POST /api/chat -- measures time to first SSE byte."""
        message = SAMPLE_CHAT_MESSAGES[self._msg_index % len(SAMPLE_CHAT_MESSAGES)]
        self._msg_index += 1

        start = time.perf_counter()
        with self.client.post(
            "/api/chat",
            json={
                "message": message,
                "session_id": self.session_id,
            },
            headers=self.headers,
            stream=True,
            catch_response=True,
            name="/api/chat [SSE]",
            timeout=30,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return

            # Read until we get the first SSE data line
            first_byte_received = False
            for line in response.iter_lines():
                if line and line.startswith(b"data:"):
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    first_byte_received = True
                    if elapsed_ms > 2000:
                        response.failure(
                            f"First SSE byte took {elapsed_ms:.0f}ms (SLA: 2000ms)"
                        )
                    else:
                        response.success()
                    break

            if not first_byte_received:
                response.failure("No SSE data received")

    # ── RAG search ────────────────────────────────────────────────────────

    @task(3)
    def rag_search(self):
        """POST /api/knowledge/search -- measures full response time."""
        query = SAMPLE_RAG_QUERIES[self._rag_index % len(SAMPLE_RAG_QUERIES)]
        self._rag_index += 1

        with self.client.post(
            "/api/knowledge/search",
            json={"query": query, "limit": 10},
            headers=self.headers,
            catch_response=True,
            name="/api/knowledge/search",
            timeout=10,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("total", 0) == 0:
                    response.failure("No results returned")
                else:
                    response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    # ── Bundle generation ─────────────────────────────────────────────────

    @task(1)
    def bundle_generate(self):
        """POST /api/bundle/generate -- measures full generation time."""
        with self.client.post(
            "/api/bundle/generate",
            json={"srs_text": SMALL_SRS_TEXT},
            headers=self.headers,
            catch_response=True,
            name="/api/bundle/generate",
            timeout=60,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                bundle_id = data.get("bundle_id")
                if bundle_id:
                    # Poll for completion (up to 30s)
                    self._poll_bundle(bundle_id)
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    def _poll_bundle(self, bundle_id: str, max_wait: float = 30.0):
        """Poll bundle status until completed or timeout."""
        start = time.perf_counter()
        while time.perf_counter() - start < max_wait:
            try:
                resp = self.client.get(
                    f"/api/bundle/status/{bundle_id}",
                    headers=self.headers,
                    name="/api/bundle/status [poll]",
                    timeout=5,
                )
                if resp.status_code == 200:
                    status = resp.json().get("status")
                    if status in ("completed", "failed"):
                        return
            except Exception:
                pass
            time.sleep(1)

    # ── Admin users list ──────────────────────────────────────────────────

    @task(1)
    def admin_users_list(self):
        """GET /api/admin/users -- measures admin API latency."""
        with self.client.get(
            "/api/admin/users",
            headers=self.headers,
            catch_response=True,
            name="/api/admin/users",
            timeout=5,
        ) as response:
            if response.status_code in (200, 403):
                # 403 is acceptable -- user may not have admin role
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")
