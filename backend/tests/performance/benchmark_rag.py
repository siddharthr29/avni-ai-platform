"""Standalone RAG benchmark -- measures retrieval performance across search modes.

Queries 100 sample questions against the pgvector knowledge base (~36K chunks)
and reports p50, p95, p99 latencies for:
  - Semantic search  (pgvector HNSW cosine similarity)
  - BM25 search      (PostgreSQL tsvector/GIN full-text)
  - Hybrid search    (RRF fusion of semantic + BM25)

Run:
    cd backend
    python -m tests.performance.benchmark_rag [--queries 100] [--top-k 10] [--dsn ...]

Requirements:
    - PostgreSQL with pgvector extension running
    - ai_knowledge_chunks table populated (run scripts/ingest_all_knowledge.py)
    - sentence-transformers installed
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

# Ensure backend/app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import settings
from app.services.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample queries (diverse Avni domain questions)
# ---------------------------------------------------------------------------

SAMPLE_QUERIES = [
    "How to create a coded concept with multiple answers?",
    "What is a program enrolment form?",
    "How to set up visit schedules for ANC?",
    "Explain skip logic in Avni forms",
    "What are form element groups?",
    "How do catchments work in Avni?",
    "Subject type registration form setup",
    "How to configure group privileges?",
    "What is the difference between program and general encounters?",
    "How to create validation rules for numeric fields?",
    "Bundle upload process for new organisation",
    "How to set up multi-select coded concepts?",
    "Explain the concept answer mapping",
    "What data types does Avni support?",
    "How to create a program exit form?",
    "What is an encounter cancellation form?",
    "How to set up address level types?",
    "Explain operational subject types",
    "How to create form mappings?",
    "What are group-based privileges?",
    "How to configure high risk assessment?",
    "What is the SRS document format?",
    "How to set up a maternal health program?",
    "Explain the concept UUID registry",
    "What are decision rules in Avni?",
    "How to create a child growth monitoring form?",
    "What is the form type for program enrolment?",
    "How to set up immunization schedules?",
    "Explain the bundle zip structure",
    "What are the standard concept answers (Yes/No)?",
    "How to configure catchment-based access control?",
    "What is the Avni ETL pipeline?",
    "How to create custom reports?",
    "Explain the voided flag in Avni entities",
    "What is the displayOrder field?",
    "How to set up a community health worker program?",
    "What are the form element data types?",
    "How to configure task assignments?",
    "Explain the organisation setup process",
    "What is the difference between concepts and concept answers?",
    "How to create a household registration?",
    "What is the Avni mobile app sync process?",
    "How to set up location hierarchies?",
    "Explain the rule engine in Avni",
    "What is the bundle diff process?",
    "How to create encounter eligibility rules?",
    "What are operational programs?",
    "How to set up PNC visit schedules?",
    "Explain the form wizard UI",
    "What is the media observation data type?",
    "How to configure notification rules?",
    "What is the Avni server API authentication?",
    "How to create a nutrition program?",
    "Explain the concept hierarchy",
    "What is the group subject type?",
    "How to set up a TB treatment program?",
    "What are the standard form types in Avni?",
    "How to configure data entry in Avni?",
    "Explain the metadata zip format",
    "What is the form version management?",
    "How to create a birth registration form?",
    "What is the subject migration feature?",
    "How to set up multi-language support?",
    "Explain the audit log in Avni",
    "What is the dashboard configuration?",
    "How to create a death registration form?",
    "What are the privilege types in Avni?",
    "How to configure custom search filters?",
    "Explain the extension system",
    "What is the news broadcast feature?",
    "How to set up a WASH program?",
    "What is the individual relationship feature?",
    "How to create a household visit form?",
    "Explain the sync concept in Avni",
    "What is the MyDashboard feature?",
    "How to configure approval workflows?",
    "What are subject type settings?",
    "How to create a checklist form?",
    "Explain the data import process",
    "What is the location hierarchy depth?",
    "How to set up a referral workflow?",
    "What is the video observation type?",
    "How to configure program colour coding?",
    "Explain the user creation process in Avni",
    "What is the catchment assignment strategy?",
    "How to create a follow-up encounter?",
    "What are encounter type settings?",
    "How to set up a community mobilization program?",
    "Explain the form element visibility rules",
    "What is the standard UUID registry?",
    "How to configure mandatory fields?",
    "What is the encounter scheduling algorithm?",
    "How to create a screening form?",
    "Explain the program enrolment eligibility",
    "What is the organisation config?",
    "How to set up a disability registry?",
    "What are coded concept search strategies?",
    "How to configure form element validation?",
    "Explain the key-value concept type",
    "What is the organisation group feature?",
]


@dataclass
class TimingResult:
    """Holds timing measurements for a single query."""
    query: str
    embedding_ms: float = 0.0
    retrieval_ms: float = 0.0
    total_ms: float = 0.0
    result_count: int = 0


@dataclass
class BenchmarkReport:
    """Aggregated statistics for a search mode."""
    mode: str
    timings: list[TimingResult] = field(default_factory=list)

    @property
    def total_times(self) -> list[float]:
        return [t.total_ms for t in self.timings]

    @property
    def embedding_times(self) -> list[float]:
        return [t.embedding_ms for t in self.timings]

    @property
    def retrieval_times(self) -> list[float]:
        return [t.retrieval_ms for t in self.timings]

    def percentile(self, values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * pct / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]

    def summary(self) -> dict:
        return {
            "mode": self.mode,
            "queries": len(self.timings),
            "total_ms": {
                "p50": round(self.percentile(self.total_times, 50), 2),
                "p95": round(self.percentile(self.total_times, 95), 2),
                "p99": round(self.percentile(self.total_times, 99), 2),
                "mean": round(statistics.mean(self.total_times), 2) if self.total_times else 0,
            },
            "embedding_ms": {
                "p50": round(self.percentile(self.embedding_times, 50), 2),
                "p95": round(self.percentile(self.embedding_times, 95), 2),
                "p99": round(self.percentile(self.embedding_times, 99), 2),
                "mean": round(statistics.mean(self.embedding_times), 2) if self.embedding_times else 0,
            },
            "retrieval_ms": {
                "p50": round(self.percentile(self.retrieval_times, 50), 2),
                "p95": round(self.percentile(self.retrieval_times, 95), 2),
                "p99": round(self.percentile(self.retrieval_times, 99), 2),
                "mean": round(statistics.mean(self.retrieval_times), 2) if self.retrieval_times else 0,
            },
            "avg_results": round(
                statistics.mean([t.result_count for t in self.timings]), 1
            ) if self.timings else 0,
        }


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

_embedder = None


def get_embedder():
    """Lazy-load the sentence-transformers model."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        model_name = getattr(settings, "EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        _embedder = SentenceTransformer(model_name)
        print(f"Loaded embedding model: {model_name}")
    return _embedder


def embed_query(query: str) -> tuple[list[float], float]:
    """Embed a single query. Returns (embedding, elapsed_ms)."""
    model = get_embedder()
    start = time.perf_counter()
    vec = model.encode(query).tolist()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return vec, elapsed_ms


# ---------------------------------------------------------------------------
# Benchmark runners
# ---------------------------------------------------------------------------

async def benchmark_semantic(
    store: VectorStore, queries: list[str], top_k: int
) -> BenchmarkReport:
    """Run semantic-only search benchmark."""
    report = BenchmarkReport(mode="semantic")

    for query in queries:
        embedding, embed_ms = embed_query(query)

        start = time.perf_counter()
        results = await store.semantic_search(embedding, top_k=top_k)
        retrieval_ms = (time.perf_counter() - start) * 1000

        report.timings.append(TimingResult(
            query=query,
            embedding_ms=embed_ms,
            retrieval_ms=retrieval_ms,
            total_ms=embed_ms + retrieval_ms,
            result_count=len(results),
        ))

    return report


async def benchmark_bm25(
    store: VectorStore, queries: list[str], top_k: int
) -> BenchmarkReport:
    """Run BM25 keyword-only search benchmark."""
    report = BenchmarkReport(mode="bm25")

    for query in queries:
        start = time.perf_counter()
        results = await store.keyword_search(query, top_k=top_k)
        retrieval_ms = (time.perf_counter() - start) * 1000

        report.timings.append(TimingResult(
            query=query,
            embedding_ms=0.0,
            retrieval_ms=retrieval_ms,
            total_ms=retrieval_ms,
            result_count=len(results),
        ))

    return report


async def benchmark_hybrid(
    store: VectorStore, queries: list[str], top_k: int
) -> BenchmarkReport:
    """Run hybrid (semantic + BM25 with RRF) search benchmark."""
    report = BenchmarkReport(mode="hybrid")

    for query in queries:
        embedding, embed_ms = embed_query(query)

        start = time.perf_counter()
        results = await store.hybrid_search(
            query_embedding=embedding,
            query_text=query,
            top_k=top_k,
        )
        retrieval_ms = (time.perf_counter() - start) * 1000

        report.timings.append(TimingResult(
            query=query,
            embedding_ms=embed_ms,
            retrieval_ms=retrieval_ms,
            total_ms=embed_ms + retrieval_ms,
            result_count=len(results),
        ))

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_benchmark(num_queries: int = 100, top_k: int = 10, dsn: str | None = None):
    """Execute all three benchmarks and print results."""
    dsn = dsn or getattr(settings, "DATABASE_URL", "postgresql://samanvay@localhost:5432/avni_ai")

    # Select queries (cycle if fewer than num_queries available)
    queries = []
    for i in range(num_queries):
        queries.append(SAMPLE_QUERIES[i % len(SAMPLE_QUERIES)])

    store = VectorStore(dsn=dsn)
    await store.initialize()

    total_chunks = await store.get_total_count()
    stats = await store.get_collection_stats()
    print(f"\nKnowledge base: {total_chunks:,} chunks across {len(stats)} collections")
    for coll, count in stats.items():
        print(f"  {coll}: {count:,}")

    print(f"\nRunning benchmarks: {num_queries} queries, top_k={top_k}")
    print("=" * 72)

    # Warm up embedding model
    print("\nWarming up embedding model...")
    embed_query("warmup query")

    # Run benchmarks
    print("\n[1/3] Semantic search...")
    semantic_report = await benchmark_semantic(store, queries, top_k)

    print("[2/3] BM25 keyword search...")
    bm25_report = await benchmark_bm25(store, queries, top_k)

    print("[3/3] Hybrid search (semantic + BM25 + RRF)...")
    hybrid_report = await benchmark_hybrid(store, queries, top_k)

    await store.close()

    # Print results
    print("\n" + "=" * 72)
    print("BENCHMARK RESULTS")
    print("=" * 72)

    for report in [semantic_report, bm25_report, hybrid_report]:
        s = report.summary()
        print(f"\n--- {s['mode'].upper()} ({s['queries']} queries) ---")
        print(f"  Total latency:     p50={s['total_ms']['p50']:>8.1f}ms  "
              f"p95={s['total_ms']['p95']:>8.1f}ms  "
              f"p99={s['total_ms']['p99']:>8.1f}ms  "
              f"mean={s['total_ms']['mean']:>8.1f}ms")
        if s['embedding_ms']['mean'] > 0:
            print(f"  Embedding time:    p50={s['embedding_ms']['p50']:>8.1f}ms  "
                  f"p95={s['embedding_ms']['p95']:>8.1f}ms  "
                  f"p99={s['embedding_ms']['p99']:>8.1f}ms  "
                  f"mean={s['embedding_ms']['mean']:>8.1f}ms")
        print(f"  Retrieval time:    p50={s['retrieval_ms']['p50']:>8.1f}ms  "
              f"p95={s['retrieval_ms']['p95']:>8.1f}ms  "
              f"p99={s['retrieval_ms']['p99']:>8.1f}ms  "
              f"mean={s['retrieval_ms']['mean']:>8.1f}ms")
        print(f"  Avg results:       {s['avg_results']}")

    # SLA check
    print("\n" + "=" * 72)
    print("SLA CHECK (RAG p95 target: < 200ms total)")
    print("=" * 72)
    for report in [semantic_report, bm25_report, hybrid_report]:
        s = report.summary()
        p95 = s["total_ms"]["p95"]
        status = "PASS" if p95 < 200 else ("WARN" if p95 < 500 else "FAIL")
        print(f"  {s['mode']:>10s}:  p95={p95:>8.1f}ms  [{status}]")

    # Write JSON report
    report_path = Path(__file__).parent / "rag_benchmark_results.json"
    results = {
        "knowledge_base": {"total_chunks": total_chunks, "collections": stats},
        "config": {"num_queries": num_queries, "top_k": top_k},
        "semantic": semantic_report.summary(),
        "bm25": bm25_report.summary(),
        "hybrid": hybrid_report.summary(),
    }
    report_path.write_text(json.dumps(results, indent=2))
    print(f"\nDetailed results written to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="RAG benchmark for Avni AI Platform")
    parser.add_argument("--queries", type=int, default=100, help="Number of queries to run")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results per query")
    parser.add_argument("--dsn", type=str, default=None, help="PostgreSQL DSN override")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_benchmark(
        num_queries=args.queries,
        top_k=args.top_k,
        dsn=args.dsn,
    ))


if __name__ == "__main__":
    main()
