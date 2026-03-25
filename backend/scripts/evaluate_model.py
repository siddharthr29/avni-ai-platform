"""Evaluate fine-tuned or base Avni models on the validation set.

Usage:
    python -m scripts.evaluate_model [--model avni-coder] [--provider ollama] [--samples 50]
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_validation_data(path: str = "training_data/clean/avni_val_clean.jsonl") -> list[dict]:
    """Load validation JSONL data."""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def evaluate_with_ollama(model: str, samples: list[dict], base_url: str = "http://localhost:11434") -> list[dict]:
    """Run evaluation against an Ollama model."""
    import httpx

    results = []
    for i, sample in enumerate(samples):
        prompt = sample.get("instruction", sample.get("input", ""))
        expected = sample.get("output", sample.get("response", ""))

        try:
            with httpx.Client(timeout=60.0) as client:
                start = time.time()
                resp = client.post(f"{base_url}/api/generate", json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                })
                elapsed = time.time() - start
                resp.raise_for_status()
                actual = resp.json().get("response", "")

                results.append({
                    "index": i,
                    "prompt": prompt[:200],
                    "expected": expected[:200],
                    "actual": actual[:200],
                    "latency_s": round(elapsed, 2),
                    "expected_len": len(expected),
                    "actual_len": len(actual),
                })

                if (i + 1) % 10 == 0:
                    logger.info("Evaluated %d/%d samples", i + 1, len(samples))
        except Exception as e:
            results.append({
                "index": i,
                "prompt": prompt[:200],
                "error": str(e),
            })

    return results


def compute_metrics(results: list[dict]) -> dict:
    """Compute evaluation metrics from results."""
    successful = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    if not successful:
        return {"error": "No successful evaluations"}

    avg_latency = sum(r["latency_s"] for r in successful) / len(successful)
    avg_expected_len = sum(r["expected_len"] for r in successful) / len(successful)
    avg_actual_len = sum(r["actual_len"] for r in successful) / len(successful)

    return {
        "total_samples": len(results),
        "successful": len(successful),
        "errors": len(errors),
        "avg_latency_s": round(avg_latency, 2),
        "avg_expected_length": round(avg_expected_len),
        "avg_actual_length": round(avg_actual_len),
        "length_ratio": round(avg_actual_len / avg_expected_len, 2) if avg_expected_len > 0 else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate Avni AI model")
    parser.add_argument("--model", default="avni-coder", help="Model name")
    parser.add_argument("--provider", default="ollama", help="Provider (ollama)")
    parser.add_argument("--samples", type=int, default=50, help="Number of samples to evaluate")
    parser.add_argument("--val-path", default="training_data/clean/avni_val_clean.jsonl")
    parser.add_argument("--output", help="Save results to JSON file")
    args = parser.parse_args()

    logger.info("Loading validation data from %s", args.val_path)
    val_data = load_validation_data(args.val_path)
    samples = val_data[:args.samples]
    logger.info("Evaluating %d samples with %s on %s", len(samples), args.model, args.provider)

    if args.provider == "ollama":
        results = evaluate_with_ollama(args.model, samples)
    else:
        logger.error("Unsupported provider: %s", args.provider)
        sys.exit(1)

    metrics = compute_metrics(results)
    logger.info("Metrics: %s", json.dumps(metrics, indent=2))

    # Print sample outputs for manual review
    print("\n--- Sample Outputs (first 5) ---\n")
    for r in results[:5]:
        if "error" in r:
            print(f"[ERROR] {r['error']}")
            continue
        print(f"Prompt: {r['prompt']}")
        print(f"Expected: {r['expected']}")
        print(f"Actual: {r['actual']}")
        print(f"Latency: {r['latency_s']}s")
        print("-" * 60)

    if args.output:
        with open(args.output, "w") as f:
            json.dump({"metrics": metrics, "results": results}, f, indent=2)
        logger.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
