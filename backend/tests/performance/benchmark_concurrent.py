"""Concurrent access benchmark -- measures throughput under parallel load.

Simulates 5, 10, 20, and 50 concurrent bundle generations to measure:
  - Throughput (bundles/second)
  - Error rate (% failed generations)
  - Latency degradation vs single-user baseline
  - Connection pool utilization (asyncpg pool stats)

Run:
    cd backend
    python -m tests.performance.benchmark_concurrent [--max-concurrency 50]
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.models.schemas import SRSData, SRSFormDefinition, SRSFormField, SRSFormGroup
from app.services.bundle_generator import generate_from_srs, _bundle_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SRS fixture (small, consistent size for concurrency testing)
# ---------------------------------------------------------------------------

def _make_concurrent_srs(worker_id: int) -> SRSData:
    """Build a small SRS (5 forms) for concurrency testing."""
    forms = [
        SRSFormDefinition(
            name=f"Registration Form W{worker_id}",
            formType="IndividualProfile",
            groups=[SRSFormGroup(
                name="Demographics",
                fields=[
                    SRSFormField(name="Name", type="Text", mandatory=True),
                    SRSFormField(name="Age", type="Numeric", mandatory=True),
                    SRSFormField(name="Gender", type="Coded", mandatory=True,
                                answers=["Male", "Female", "Other"]),
                ],
            )],
        ),
        SRSFormDefinition(
            name=f"Enrolment Form W{worker_id}",
            formType="ProgramEnrolment",
            programName="Health Program",
            groups=[SRSFormGroup(
                name="Enrolment Details",
                fields=[
                    SRSFormField(name="Enrolment Date", type="Date", mandatory=True),
                    SRSFormField(name="High Risk", type="Coded", answers=["Yes", "No"]),
                ],
            )],
        ),
        SRSFormDefinition(
            name=f"Visit Form W{worker_id}",
            formType="ProgramEncounter",
            programName="Health Program",
            encounterName="Health Visit",
            groups=[SRSFormGroup(
                name="Vitals",
                fields=[
                    SRSFormField(name="Weight", type="Numeric", unit="kg"),
                    SRSFormField(name="Height", type="Numeric", unit="cm"),
                    SRSFormField(name="BP Systolic", type="Numeric", unit="mmHg"),
                    SRSFormField(name="BP Diastolic", type="Numeric", unit="mmHg"),
                ],
            )],
        ),
        SRSFormDefinition(
            name=f"Exit Form W{worker_id}",
            formType="ProgramExit",
            programName="Health Program",
            groups=[SRSFormGroup(
                name="Exit Details",
                fields=[
                    SRSFormField(name="Exit Date", type="Date", mandatory=True),
                    SRSFormField(name="Exit Reason", type="Coded",
                                answers=["Completed", "Dropped Out", "Transferred", "Deceased"]),
                ],
            )],
        ),
        SRSFormDefinition(
            name=f"General Encounter W{worker_id}",
            formType="Encounter",
            encounterName="General Check-up",
            groups=[SRSFormGroup(
                name="Assessment",
                fields=[
                    SRSFormField(name="Complaints", type="Text"),
                    SRSFormField(name="Diagnosis", type="Text"),
                    SRSFormField(name="Follow-up Required", type="Coded", answers=["Yes", "No"]),
                ],
            )],
        ),
    ]

    return SRSData(
        orgName=f"Concurrent Test Org W{worker_id}",
        subjectTypes=[{"name": "Individual", "type": "Person"}],
        programs=[{"name": "Health Program", "colour": "#4CAF50"}],
        encounterTypes=["Health Visit", "General Check-up"],
        forms=forms,
    )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class WorkerResult:
    """Result from a single concurrent worker."""
    worker_id: int
    success: bool
    latency_ms: float
    error: str = ""


@dataclass
class ConcurrencyResult:
    """Aggregated results for a concurrency level."""
    concurrency: int
    workers: list[WorkerResult] = field(default_factory=list)

    @property
    def successes(self) -> int:
        return sum(1 for w in self.workers if w.success)

    @property
    def failures(self) -> int:
        return sum(1 for w in self.workers if not w.success)

    @property
    def error_rate(self) -> float:
        if not self.workers:
            return 0.0
        return self.failures / len(self.workers) * 100

    @property
    def latencies(self) -> list[float]:
        return [w.latency_ms for w in self.workers if w.success]

    @property
    def throughput(self) -> float:
        """Bundles per second based on total wall-clock time."""
        if not self.latencies:
            return 0.0
        total_wall_ms = max(self.latencies)  # All ran in parallel
        if total_wall_ms == 0:
            return 0.0
        return self.successes / (total_wall_ms / 1000)

    def percentile(self, pct: float) -> float:
        if not self.latencies:
            return 0.0
        sorted_vals = sorted(self.latencies)
        idx = min(int(len(sorted_vals) * pct / 100), len(sorted_vals) - 1)
        return sorted_vals[idx]

    def summary(self) -> dict:
        return {
            "concurrency": self.concurrency,
            "total": len(self.workers),
            "successes": self.successes,
            "failures": self.failures,
            "error_rate_pct": round(self.error_rate, 1),
            "throughput_per_sec": round(self.throughput, 2),
            "latency_ms": {
                "p50": round(self.percentile(50), 1),
                "p95": round(self.percentile(95), 1),
                "p99": round(self.percentile(99), 1),
                "mean": round(statistics.mean(self.latencies), 1) if self.latencies else 0,
                "max": round(max(self.latencies), 1) if self.latencies else 0,
            },
        }


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

async def _worker(worker_id: int, semaphore: asyncio.Semaphore) -> WorkerResult:
    """Single concurrent bundle generation worker."""
    async with semaphore:
        srs = _make_concurrent_srs(worker_id)

        start = time.perf_counter()
        try:
            # generate_from_srs is synchronous; run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            bundle_id = await loop.run_in_executor(None, generate_from_srs, srs)
            latency_ms = (time.perf_counter() - start) * 1000

            # Verify the bundle was generated
            status = _bundle_store.get(bundle_id)
            if status and status.status == "completed":
                _bundle_store.pop(bundle_id, None)
                return WorkerResult(
                    worker_id=worker_id,
                    success=True,
                    latency_ms=latency_ms,
                )
            else:
                error_msg = ""
                if status:
                    error_msg = status.error or f"status={status.status}"
                _bundle_store.pop(bundle_id, None)
                return WorkerResult(
                    worker_id=worker_id,
                    success=False,
                    latency_ms=latency_ms,
                    error=error_msg or "Bundle not completed",
                )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return WorkerResult(
                worker_id=worker_id,
                success=False,
                latency_ms=latency_ms,
                error=str(e),
            )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

CONCURRENCY_LEVELS = [1, 5, 10, 20, 50]


async def run_benchmark(max_concurrency: int = 50):
    """Run concurrent bundle generation at increasing concurrency levels."""
    print("Concurrent Bundle Generation Benchmark")
    print("=" * 72)
    print(f"Max concurrency: {max_concurrency}")
    print(f"Each worker generates a 5-form bundle")

    levels = [c for c in CONCURRENCY_LEVELS if c <= max_concurrency]
    results: list[ConcurrencyResult] = []

    # Baseline: single worker
    print("\n--- Baseline (1 worker) ---")
    baseline_result = ConcurrencyResult(concurrency=1)
    sem = asyncio.Semaphore(1)
    worker_result = await _worker(0, sem)
    baseline_result.workers.append(worker_result)
    baseline_latency = worker_result.latency_ms
    print(f"  Baseline latency: {baseline_latency:.1f}ms")
    results.append(baseline_result)

    # Concurrent levels
    for concurrency in levels:
        if concurrency == 1:
            continue  # Already ran baseline

        print(f"\n--- {concurrency} concurrent workers ---")
        result = ConcurrencyResult(concurrency=concurrency)
        sem = asyncio.Semaphore(concurrency)

        start = time.perf_counter()
        tasks = [_worker(i, sem) for i in range(concurrency)]
        worker_results = await asyncio.gather(*tasks)
        wall_time_ms = (time.perf_counter() - start) * 1000

        for wr in worker_results:
            result.workers.append(wr)

        s = result.summary()
        degradation = (s["latency_ms"]["p50"] / baseline_latency - 1) * 100 if baseline_latency > 0 else 0

        print(f"  Success: {s['successes']}/{s['total']}  "
              f"Error rate: {s['error_rate_pct']:.1f}%")
        print(f"  Latency p50={s['latency_ms']['p50']:.1f}ms  "
              f"p95={s['latency_ms']['p95']:.1f}ms  "
              f"max={s['latency_ms']['max']:.1f}ms")
        print(f"  Throughput: {s['throughput_per_sec']:.2f} bundles/sec  "
              f"Wall time: {wall_time_ms:.0f}ms")
        print(f"  Latency degradation vs baseline: {degradation:+.1f}%")

        if result.failures > 0:
            errors = [w.error for w in result.workers if not w.success]
            unique_errors = set(errors)
            for err in unique_errors:
                count = errors.count(err)
                print(f"  Error ({count}x): {err[:80]}")

        results.append(result)

    # Summary table
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"{'Conc':>5} {'OK':>4} {'Fail':>4} {'Err%':>6} "
          f"{'p50(ms)':>9} {'p95(ms)':>9} {'max(ms)':>9} "
          f"{'Tput/s':>8} {'Degrad':>8}")
    print("-" * 72)

    for r in results:
        s = r.summary()
        degradation = (s["latency_ms"]["p50"] / baseline_latency - 1) * 100 if baseline_latency > 0 else 0
        print(f"{s['concurrency']:>5} {s['successes']:>4} {s['failures']:>4} "
              f"{s['error_rate_pct']:>5.1f}% "
              f"{s['latency_ms']['p50']:>9.1f} {s['latency_ms']['p95']:>9.1f} "
              f"{s['latency_ms']['max']:>9.1f} "
              f"{s['throughput_per_sec']:>8.2f} {degradation:>+7.1f}%")

    # Connection pool analysis
    print("\n" + "=" * 72)
    print("CONNECTION POOL ANALYSIS")
    print("=" * 72)
    print("Note: Bundle generation (generate_from_srs) is CPU-bound and does not")
    print("use the database connection pool directly. Pool pressure comes from")
    print("concurrent RAG queries and chat sessions hitting pgvector.")
    print()
    print("pgvector VectorStore pool config: min_size=2, max_size=10")
    print()
    print("Recommendations based on concurrency results:")
    for r in results:
        s = r.summary()
        if s["concurrency"] <= 10:
            pool_rec = "Default pool (2-10) sufficient"
        elif s["concurrency"] <= 20:
            pool_rec = "Consider min_size=5, max_size=20"
        else:
            pool_rec = "Increase to min_size=10, max_size=50; consider read replicas"
        print(f"  {s['concurrency']:>3} concurrent: {pool_rec}")

    # Write JSON report
    report_path = Path(__file__).parent / "concurrent_benchmark_results.json"
    report_data = {
        "config": {
            "max_concurrency": max_concurrency,
            "forms_per_worker": 5,
            "pool_config": {"min_size": 2, "max_size": 10},
        },
        "baseline_latency_ms": round(baseline_latency, 1),
        "results": [r.summary() for r in results],
    }
    report_path.write_text(json.dumps(report_data, indent=2))
    print(f"\nDetailed results written to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Concurrent bundle generation benchmark")
    parser.add_argument("--max-concurrency", type=int, default=50,
                        help="Maximum concurrency level to test (default: 50)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_benchmark(max_concurrency=args.max_concurrency))


if __name__ == "__main__":
    main()
