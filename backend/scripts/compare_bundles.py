"""Compare AI-generated bundles against production/reference bundles.

Usage:
    python -m scripts.compare_bundles --generated <path> --reference <path> [--output report.json] [--verbose]

Supports both directory bundles and ZIP bundles (auto-extracted).
"""

import argparse
import json
import os
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class EntityComparison:
    entity_type: str
    total_reference: int = 0
    total_generated: int = 0
    matched: int = 0
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    mismatched: list[dict] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.matched / self.total_generated if self.total_generated > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.matched / self.total_reference if self.total_reference > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


def _normalize_name(name: str) -> str:
    """Normalize entity name for comparison."""
    return name.strip().lower().replace("_", " ").replace("-", " ")


def _load_json_files(directory: str, pattern: str = "*.json") -> list[dict]:
    """Load all JSON files from a directory matching a pattern."""
    results = []
    dir_path = Path(directory)
    if not dir_path.exists():
        return results
    for f in sorted(dir_path.rglob(pattern)):
        try:
            with open(f) as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    results.extend(data)
                elif isinstance(data, dict):
                    results.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _extract_zip(zip_path: str) -> str:
    """Extract ZIP to temp directory and return path."""
    tmp_dir = tempfile.mkdtemp(prefix="bundle_compare_")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_dir)
    return tmp_dir


def _load_bundle(path: str) -> dict[str, list[dict]]:
    """Load a bundle from directory or ZIP, returning entities by type."""
    if path.endswith(".zip"):
        path = _extract_zip(path)

    bundle: dict[str, list[dict]] = {
        "concepts": [],
        "forms": [],
        "encounterTypes": [],
        "programs": [],
        "subjectTypes": [],
        "formMappings": [],
    }

    p = Path(path)
    # Try loading from standard Avni bundle structure
    for entity_type in bundle:
        entity_dir = p / entity_type
        if entity_dir.is_dir():
            bundle[entity_type] = _load_json_files(str(entity_dir))
        # Also try flat files
        flat_file = p / f"{entity_type}.json"
        if flat_file.exists() and not bundle[entity_type]:
            try:
                with open(flat_file) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        bundle[entity_type] = data
                    elif isinstance(data, dict):
                        bundle[entity_type] = [data]
            except (json.JSONDecodeError, OSError):
                pass

    return bundle


def _get_name(entity: dict) -> str:
    """Extract the name from an entity, trying common field names."""
    for key in ("name", "Name", "concept", "formName", "encounterType", "programName", "subjectType"):
        if key in entity:
            return str(entity[key])
    return entity.get("uuid", "unknown")


def compare_concepts(gen: list[dict], ref: list[dict]) -> EntityComparison:
    """Compare concepts between generated and reference bundles."""
    comp = EntityComparison(entity_type="concepts")

    ref_by_name = {_normalize_name(_get_name(c)): c for c in ref}
    gen_by_name = {_normalize_name(_get_name(c)): c for c in gen}

    comp.total_reference = len(ref_by_name)
    comp.total_generated = len(gen_by_name)

    for name in ref_by_name:
        if name not in gen_by_name:
            comp.missing.append(name)

    for name in gen_by_name:
        if name not in ref_by_name:
            comp.extra.append(name)

    for name in set(ref_by_name) & set(gen_by_name):
        ref_c = ref_by_name[name]
        gen_c = gen_by_name[name]
        mismatches = []

        # Check dataType
        ref_dt = ref_c.get("dataType", "")
        gen_dt = gen_c.get("dataType", "")
        if ref_dt and gen_dt and ref_dt != gen_dt:
            mismatches.append({"field": "dataType", "reference": ref_dt, "generated": gen_dt})

        # Check coded answers
        ref_answers = set(_normalize_name(a.get("name", a) if isinstance(a, dict) else str(a))
                         for a in ref_c.get("answers", ref_c.get("conceptAnswers", [])))
        gen_answers = set(_normalize_name(a.get("name", a) if isinstance(a, dict) else str(a))
                         for a in gen_c.get("answers", gen_c.get("conceptAnswers", [])))
        if ref_answers or gen_answers:
            missing_answers = ref_answers - gen_answers
            extra_answers = gen_answers - ref_answers
            if missing_answers or extra_answers:
                mismatches.append({
                    "field": "answers",
                    "missing": list(missing_answers),
                    "extra": list(extra_answers),
                })

        if mismatches:
            comp.mismatched.append({"name": name, "issues": mismatches})
        else:
            comp.matched += 1

    return comp


def compare_entities(gen: list[dict], ref: list[dict], entity_type: str) -> EntityComparison:
    """Generic comparison for forms, encounter types, programs, subject types."""
    comp = EntityComparison(entity_type=entity_type)

    ref_by_name = {_normalize_name(_get_name(e)): e for e in ref}
    gen_by_name = {_normalize_name(_get_name(e)): e for e in gen}

    comp.total_reference = len(ref_by_name)
    comp.total_generated = len(gen_by_name)

    for name in ref_by_name:
        if name not in gen_by_name:
            comp.missing.append(name)

    for name in gen_by_name:
        if name not in ref_by_name:
            comp.extra.append(name)

    comp.matched = len(set(ref_by_name) & set(gen_by_name))
    return comp


def compare_bundles(generated_path: str, reference_path: str, verbose: bool = False) -> dict:
    """Compare two bundles and return a detailed report."""
    gen_bundle = _load_bundle(generated_path)
    ref_bundle = _load_bundle(reference_path)

    results: dict[str, EntityComparison] = {}

    # Concepts get special comparison (dataType, answers)
    results["concepts"] = compare_concepts(
        gen_bundle["concepts"], ref_bundle["concepts"]
    )

    # Other entity types
    for entity_type in ["forms", "encounterTypes", "programs", "subjectTypes", "formMappings"]:
        results[entity_type] = compare_entities(
            gen_bundle[entity_type], ref_bundle[entity_type], entity_type
        )

    # Overall score
    total_ref = sum(r.total_reference for r in results.values())
    total_matched = sum(r.matched for r in results.values())
    overall_match = (total_matched / total_ref * 100) if total_ref > 0 else 0.0

    report = {
        "overall_match_percentage": round(overall_match, 1),
        "total_reference_entities": total_ref,
        "total_generated_entities": sum(r.total_generated for r in results.values()),
        "total_matched": total_matched,
        "entity_comparisons": {},
    }

    for entity_type, comp in results.items():
        entry = {
            "total_reference": comp.total_reference,
            "total_generated": comp.total_generated,
            "matched": comp.matched,
            "precision": round(comp.precision * 100, 1),
            "recall": round(comp.recall * 100, 1),
            "f1": round(comp.f1 * 100, 1),
            "missing_count": len(comp.missing),
            "extra_count": len(comp.extra),
            "mismatch_count": len(comp.mismatched),
        }
        if verbose:
            entry["missing"] = comp.missing
            entry["extra"] = comp.extra
            entry["mismatched"] = comp.mismatched
        report["entity_comparisons"][entity_type] = entry

    return report


def main():
    parser = argparse.ArgumentParser(description="Compare Avni bundles")
    parser.add_argument("--generated", required=True, help="Path to generated bundle (dir or ZIP)")
    parser.add_argument("--reference", required=True, help="Path to reference bundle (dir or ZIP)")
    parser.add_argument("--output", help="Output report to JSON file")
    parser.add_argument("--verbose", action="store_true", help="Include detailed mismatch info")
    args = parser.parse_args()

    report = compare_bundles(args.generated, args.reference, args.verbose)

    output = json.dumps(report, indent=2)
    print(output)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"\nReport saved to {args.output}")

    # Exit with non-zero if match < 50%
    sys.exit(0 if report["overall_match_percentage"] >= 50 else 1)


if __name__ == "__main__":
    main()
