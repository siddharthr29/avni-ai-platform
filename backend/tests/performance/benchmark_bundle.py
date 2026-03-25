"""Bundle generation benchmark -- measures performance across SRS sizes.

Generates Avni implementation bundles from five different SRS complexity levels
and reports per-size metrics: parse time, generation time, validation time, total.

SRS Sizes:
    tiny   :  2 forms  (baseline)
    small  :  5 forms
    medium : 15 forms
    large  : 30 forms
    xlarge : 50 forms  (stress test)

Run:
    cd backend
    python -m tests.performance.benchmark_bundle [--iterations 3]
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.models.schemas import SRSData, SRSFormDefinition, SRSFormField, SRSFormGroup
from app.services.bundle_generator import generate_from_srs, _bundle_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SRS fixture generators
# ---------------------------------------------------------------------------

CODED_ANSWERS = ["Yes", "No", "Unknown", "Not Applicable"]
GENDER_ANSWERS = ["Male", "Female", "Other"]
CASTE_ANSWERS = ["SC", "ST", "OBC", "General"]

FIELD_TEMPLATES: list[dict[str, Any]] = [
    {"name": "Name", "type": "Text", "mandatory": True},
    {"name": "Age", "type": "Numeric", "mandatory": True},
    {"name": "Date of Birth", "type": "Date", "mandatory": False},
    {"name": "Gender", "type": "Coded", "answers": GENDER_ANSWERS, "mandatory": True},
    {"name": "Phone Number", "type": "Text", "mandatory": False},
    {"name": "Weight", "type": "Numeric", "unit": "kg", "mandatory": False},
    {"name": "Height", "type": "Numeric", "unit": "cm", "mandatory": False},
    {"name": "BP Systolic", "type": "Numeric", "unit": "mmHg", "mandatory": False},
    {"name": "BP Diastolic", "type": "Numeric", "unit": "mmHg", "mandatory": False},
    {"name": "Temperature", "type": "Numeric", "unit": "F", "mandatory": False},
    {"name": "Is High Risk", "type": "Coded", "answers": ["Yes", "No"], "mandatory": False},
    {"name": "Caste", "type": "Coded", "answers": CASTE_ANSWERS, "mandatory": False},
    {"name": "Address", "type": "Text", "mandatory": False},
    {"name": "Remarks", "type": "Notes", "mandatory": False},
    {"name": "Photo", "type": "Image", "mandatory": False},
]

FORM_TYPE_CYCLE = [
    "IndividualProfile",
    "ProgramEnrolment",
    "ProgramEncounter",
    "ProgramEncounter",
    "ProgramExit",
    "ProgramEncounter",
    "Encounter",
    "ProgramEncounter",
    "ProgramEncounterCancellation",
    "ProgramEncounter",
]

PROGRAM_NAMES = [
    "Maternal Health", "Child Health", "Nutrition", "Immunization",
    "TB Treatment", "Adolescent Health", "Family Planning", "NCD Screening",
]

ENCOUNTER_TYPE_NAMES = [
    "ANC Visit", "PNC Visit", "Growth Monitoring", "Vaccination",
    "Follow-up", "Screening", "Counselling", "Home Visit",
    "Lab Test", "Referral", "Community Meeting", "Training Session",
]


def _make_fields(count: int) -> list[SRSFormField]:
    """Generate a list of form fields by cycling through templates."""
    fields = []
    for i in range(count):
        tmpl = FIELD_TEMPLATES[i % len(FIELD_TEMPLATES)]
        suffix = f" {i // len(FIELD_TEMPLATES) + 1}" if i >= len(FIELD_TEMPLATES) else ""
        f = SRSFormField(
            name=tmpl["name"] + suffix,
            type=tmpl["type"],
            mandatory=tmpl.get("mandatory", False),
            answers=tmpl.get("answers"),
            unit=tmpl.get("unit"),
        )
        fields.append(f)
    return fields


def _make_srs(num_forms: int) -> SRSData:
    """Build an SRS fixture with the specified number of forms."""
    forms = []
    programs_used = set()
    encounter_types_used = set()

    for i in range(num_forms):
        form_type = FORM_TYPE_CYCLE[i % len(FORM_TYPE_CYCLE)]
        fields_per_form = 5 + (i % 11)  # 5 to 15 fields per form

        program_name = PROGRAM_NAMES[i % len(PROGRAM_NAMES)]
        encounter_name = ENCOUNTER_TYPE_NAMES[i % len(ENCOUNTER_TYPE_NAMES)]

        form_name = f"Form {i + 1} - {encounter_name}"
        if form_type == "IndividualProfile":
            form_name = f"Registration Form {i + 1}"
            program_name = None
            encounter_name = None
        elif form_type in ("ProgramEnrolment", "ProgramExit"):
            encounter_name = None
        else:
            programs_used.add(program_name)
            encounter_types_used.add(encounter_name)

        if program_name:
            programs_used.add(program_name)

        # Split fields into 1-3 groups
        all_fields = _make_fields(fields_per_form)
        groups = []
        group_size = max(3, fields_per_form // 2)
        for gi in range(0, len(all_fields), group_size):
            group_fields = all_fields[gi : gi + group_size]
            groups.append(SRSFormGroup(
                name=f"Section {gi // group_size + 1}",
                fields=group_fields,
            ))

        form_def = SRSFormDefinition(
            name=form_name,
            formType=form_type,
            programName=program_name,
            encounterName=encounter_name,
            groups=groups,
        )
        forms.append(form_def)

    programs = [{"name": p, "colour": "#E91E63"} for p in sorted(programs_used)]
    encounter_types = sorted(encounter_types_used)

    return SRSData(
        orgName=f"Benchmark Org ({num_forms} forms)",
        subjectTypes=[{"name": "Individual", "type": "Person"}],
        programs=programs,
        encounterTypes=encounter_types,
        forms=forms,
    )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

@dataclass
class SizeResult:
    """Results for a single SRS size."""
    size_label: str
    num_forms: int
    iterations: list[dict[str, float]] = field(default_factory=list)

    def add(self, parse_ms: float, generate_ms: float, validate_ms: float, total_ms: float):
        self.iterations.append({
            "parse_ms": parse_ms,
            "generate_ms": generate_ms,
            "validate_ms": validate_ms,
            "total_ms": total_ms,
        })

    def _stat(self, key: str) -> dict[str, float]:
        values = [it[key] for it in self.iterations]
        if not values:
            return {"mean": 0, "min": 0, "max": 0, "stddev": 0}
        return {
            "mean": round(statistics.mean(values), 1),
            "min": round(min(values), 1),
            "max": round(max(values), 1),
            "stddev": round(statistics.stdev(values), 1) if len(values) > 1 else 0,
        }

    def summary(self) -> dict:
        return {
            "size": self.size_label,
            "num_forms": self.num_forms,
            "iterations": len(self.iterations),
            "parse_ms": self._stat("parse_ms"),
            "generate_ms": self._stat("generate_ms"),
            "validate_ms": self._stat("validate_ms"),
            "total_ms": self._stat("total_ms"),
        }


SIZE_CONFIGS = [
    ("tiny", 2),
    ("small", 5),
    ("medium", 15),
    ("large", 30),
    ("xlarge", 50),
]


def _validate_bundle_zip(zip_path: str) -> tuple[bool, float]:
    """Validate generated bundle zip. Returns (is_valid, elapsed_ms)."""
    start = time.perf_counter()

    if not Path(zip_path).exists():
        return False, (time.perf_counter() - start) * 1000

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # Must contain at least concepts.json and one form file
            has_concepts = any("concepts.json" in n for n in names)
            has_forms = any("forms/" in n or "Form" in n for n in names)
            # Validate JSON is parseable
            for name in names:
                if name.endswith(".json"):
                    data = zf.read(name)
                    json.loads(data)

            valid = has_concepts and has_forms and len(names) >= 3
    except Exception:
        valid = False

    elapsed_ms = (time.perf_counter() - start) * 1000
    return valid, elapsed_ms


async def run_benchmark(iterations: int = 3):
    """Execute bundle generation benchmarks for all sizes."""
    print("Bundle Generation Benchmark")
    print("=" * 72)
    print(f"Iterations per size: {iterations}")

    results: list[SizeResult] = []

    for size_label, num_forms in SIZE_CONFIGS:
        print(f"\n--- {size_label.upper()} ({num_forms} forms) ---")
        result = SizeResult(size_label=size_label, num_forms=num_forms)

        for iteration in range(iterations):
            # Phase 1: Parse (build SRS data structure)
            parse_start = time.perf_counter()
            srs = _make_srs(num_forms)
            parse_ms = (time.perf_counter() - parse_start) * 1000

            # Phase 2: Generate bundle
            gen_start = time.perf_counter()
            bundle_id = generate_from_srs(srs)
            gen_ms = (time.perf_counter() - gen_start) * 1000

            # Phase 3: Validate output
            status = _bundle_store.get(bundle_id)
            zip_path = ""
            if status and status.zip_path:
                zip_path = status.zip_path

            valid, validate_ms = _validate_bundle_zip(zip_path) if zip_path else (False, 0.0)

            total_ms = parse_ms + gen_ms + validate_ms
            result.add(parse_ms, gen_ms, validate_ms, total_ms)

            status_str = "OK" if valid else "INVALID"
            print(f"  [{iteration + 1}/{iterations}] "
                  f"parse={parse_ms:>7.1f}ms  gen={gen_ms:>8.1f}ms  "
                  f"validate={validate_ms:>6.1f}ms  total={total_ms:>8.1f}ms  "
                  f"[{status_str}]")

            # Clean up generated bundle from in-memory store
            _bundle_store.pop(bundle_id, None)

        results.append(result)

    # Summary table
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"{'Size':<8} {'Forms':>5} {'Parse (ms)':>12} {'Generate (ms)':>14} "
          f"{'Validate (ms)':>14} {'Total (ms)':>12}")
    print("-" * 72)

    for r in results:
        s = r.summary()
        print(f"{s['size']:<8} {s['num_forms']:>5} "
              f"{s['parse_ms']['mean']:>12.1f} "
              f"{s['generate_ms']['mean']:>14.1f} "
              f"{s['validate_ms']['mean']:>14.1f} "
              f"{s['total_ms']['mean']:>12.1f}")

    # SLA check
    print("\n" + "=" * 72)
    print("SLA CHECK (Bundle p95 target: < 30s)")
    print("=" * 72)
    for r in results:
        s = r.summary()
        max_ms = s["total_ms"]["max"]
        status = "PASS" if max_ms < 30000 else "FAIL"
        print(f"  {s['size']:>8s} ({s['num_forms']:>2d} forms): "
              f"max={max_ms:>10.1f}ms  [{status}]")

    # Write JSON report
    report_path = Path(__file__).parent / "bundle_benchmark_results.json"
    report_data = {
        "config": {"iterations": iterations, "sizes": SIZE_CONFIGS},
        "results": [r.summary() for r in results],
    }
    report_path.write_text(json.dumps(report_data, indent=2))
    print(f"\nDetailed results written to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Bundle generation benchmark")
    parser.add_argument("--iterations", type=int, default=3,
                        help="Number of iterations per size (default: 3)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_benchmark(iterations=args.iterations))


if __name__ == "__main__":
    main()
