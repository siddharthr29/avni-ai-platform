#!/usr/bin/env python3
"""Prepare fine-tuning training data from Avni implementation bundles.

Extracts question-answer pairs from real implementation bundles, production rules,
form patterns, and knowledge base to create training data for the self-hosted model.

Output: JSONL files in OpenAI fine-tuning format (compatible with Ollama/Unsloth/Axolotl):
  {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

Usage:
    python scripts/prepare_training_data.py \
        --bundles-dir ~/Downloads/All/avni-ai/impl-bundles/ \
        --knowledge-dir app/knowledge/data/ \
        --output-dir training_data/

    # Include production DB exports
    python scripts/prepare_training_data.py \
        --bundles-dir ~/Downloads/All/avni-ai/impl-bundles/ \
        --knowledge-dir app/knowledge/data/ \
        --db-export /tmp/avni_db_knowledge/ \
        --output-dir training_data/
"""

import argparse
import glob
import json
import logging
import os
import re
import sys
import uuid

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prepare_training_data")

SYSTEM_PROMPT = (
    "You are the Avni Platform Architect. Generate exact Avni bundle JSON, "
    "JavaScript rules, and declarative rules. Use provided concept names and UUIDs. "
    "Output only code, no explanations unless asked."
)

# ---------------------------------------------------------------------------
# Training pair generators
# ---------------------------------------------------------------------------

def extract_concept_pairs(concepts_file: str) -> list[dict]:
    """Generate training pairs from concepts.json files."""
    pairs = []
    try:
        with open(concepts_file, "r") as f:
            concepts = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return pairs

    if not isinstance(concepts, list):
        return pairs

    for concept in concepts:
        name = concept.get("name", "")
        dtype = concept.get("dataType", "")
        if not name or not dtype:
            continue

        # Pair 1: "Create a concept for X" -> concept JSON
        user_msg = f"Create an Avni concept for '{name}' with data type {dtype}"
        if dtype == "Coded" and concept.get("answers"):
            answers = [a.get("answerConcept", {}).get("name", "") for a in concept["answers"] if a.get("answerConcept")]
            user_msg += f" with answers: {', '.join(answers)}"
        if dtype == "Numeric":
            parts = []
            if concept.get("lowAbsolute") is not None:
                parts.append(f"min={concept['lowAbsolute']}")
            if concept.get("highAbsolute") is not None:
                parts.append(f"max={concept['highAbsolute']}")
            if concept.get("unit"):
                parts.append(f"unit={concept['unit']}")
            if parts:
                user_msg += f" ({', '.join(parts)})"

        pairs.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": json.dumps(concept, indent=2)},
            ]
        })

    return pairs


def extract_form_pairs(forms_dir: str) -> list[dict]:
    """Generate training pairs from form JSON files."""
    pairs = []
    form_files = glob.glob(os.path.join(forms_dir, "*.json"))

    for form_file in form_files:
        try:
            with open(form_file, "r") as f:
                form_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            continue

        if not isinstance(form_data, dict):
            continue

        form_name = form_data.get("name", os.path.basename(form_file))
        form_type = form_data.get("formType", "")
        groups = form_data.get("formElementGroups", [])

        if not form_type or not groups:
            continue

        # Count elements
        total_elements = sum(
            len(g.get("formElements", []))
            for g in groups
        )

        # Extract field names
        field_names = []
        for g in groups:
            for fe in g.get("formElements", []):
                concept = fe.get("concept", {})
                if concept.get("name"):
                    field_names.append(concept["name"])

        if not field_names:
            continue

        # Training pair: describe what form to create -> get the JSON
        user_msg = (
            f"Create an Avni {form_type} form called '{form_name}' "
            f"with {len(groups)} groups and {total_elements} fields. "
            f"Fields include: {', '.join(field_names[:15])}"
        )
        if len(field_names) > 15:
            user_msg += f" and {len(field_names) - 15} more"

        # Truncate large forms for training (keep structure, limit size)
        form_str = json.dumps(form_data, indent=2)
        if len(form_str) > 12000:
            # Keep first 2 groups fully, summarize rest
            truncated = dict(form_data)
            if len(groups) > 2:
                truncated["formElementGroups"] = groups[:2]
                truncated["_note"] = f"Truncated: {len(groups) - 2} more groups omitted"
            form_str = json.dumps(truncated, indent=2)

        pairs.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": form_str},
            ]
        })

    return pairs


def extract_rule_pairs(forms_dir: str) -> list[dict]:
    """Extract rules embedded in form elements as training pairs."""
    pairs = []
    form_files = glob.glob(os.path.join(forms_dir, "*.json"))

    for form_file in form_files:
        try:
            with open(form_file, "r") as f:
                form_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            continue

        form_type = form_data.get("formType", "")

        for group in form_data.get("formElementGroups", []):
            for fe in group.get("formElements", []):
                rule = fe.get("rule")
                if not rule:
                    continue

                concept_name = fe.get("concept", {}).get("name", "unknown")
                concept_dtype = fe.get("concept", {}).get("dataType", "")

                # Try to parse the rule to understand what it does
                rule_str = str(rule)

                # Declarative rule
                if isinstance(rule, str) and rule.strip().startswith("["):
                    try:
                        rule_json = json.loads(rule)
                        # Extract the condition description
                        desc = _describe_declarative_rule(rule_json, form_type)
                        user_msg = (
                            f"Write a declarative rule for a {form_type} form element '{concept_name}' ({concept_dtype}): {desc}"
                        )
                        pairs.append({
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": user_msg},
                                {"role": "assistant", "content": json.dumps(rule_json, indent=2)},
                            ]
                        })
                    except json.JSONDecodeError:
                        pass

                # JavaScript rule
                elif isinstance(rule, str) and ("statusBuilder" in rule or "FormElementStatusBuilder" in rule):
                    desc = _describe_js_rule(rule, form_type)
                    user_msg = (
                        f"Write a JavaScript ViewFilter rule for a {form_type} form element '{concept_name}': {desc}"
                    )
                    pairs.append({
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg},
                            {"role": "assistant", "content": rule},
                        ]
                    })

    return pairs


def _describe_declarative_rule(rule_json: list, form_type: str) -> str:
    """Generate a natural language description of a declarative rule."""
    if not rule_json or not isinstance(rule_json, list):
        return "skip logic rule"

    parts = []
    for rule_block in rule_json:
        actions = rule_block.get("actions", [])
        conditions = rule_block.get("conditions", [])

        action_types = [a.get("actionType", "") for a in actions]
        parts.append(f"Actions: {', '.join(action_types)}")

        for cond in conditions:
            compound = cond.get("compoundRule", {})
            for r in compound.get("rules", []):
                lhs = r.get("lhs", {})
                op = r.get("operator", "")
                rhs = r.get("rhs", {})
                concept_name = lhs.get("conceptName", "?")
                scope = lhs.get("scope", "encounter")

                if op == "containsAnswerConceptName":
                    answers = rhs.get("answerConceptNames", [])
                    parts.append(f"Show when {concept_name} (scope: {scope}) contains {', '.join(answers)}")
                elif op == "defined":
                    parts.append(f"Show when {concept_name} (scope: {scope}) is defined")
                elif op == "notDefined":
                    parts.append(f"Show when {concept_name} (scope: {scope}) is not defined")
                else:
                    parts.append(f"When {concept_name} {op} (scope: {scope})")

    return ". ".join(parts) if parts else "skip logic rule"


def _describe_js_rule(rule: str, form_type: str) -> str:
    """Generate a natural language description of a JS rule."""
    parts = []

    # Extract valueInEncounter/valueInEnrolment patterns
    for match in re.finditer(r'valueIn(\w+)\("([^"]+)"\)', rule):
        scope = match.group(1)
        concept = match.group(2)
        parts.append(f"checks {concept} in {scope}")

    # Extract containsAnswerConceptName
    for match in re.finditer(r'containsAnswerConceptName\("([^"]+)"\)', rule):
        parts.append(f"matches answer '{match.group(1)}'")

    # Extract show/hide
    if "show()" in rule:
        parts.insert(0, "Show element when")
    if "skipAnswers" in rule:
        parts.insert(0, "Skip certain answers when")

    return ". ".join(parts) if parts else "skip logic rule"


def extract_form_mapping_pairs(bundle_dir: str) -> list[dict]:
    """Generate training pairs from formMappings.json."""
    pairs = []
    mapping_file = os.path.join(bundle_dir, "formMappings.json")
    if not os.path.isfile(mapping_file):
        return pairs

    try:
        with open(mapping_file, "r") as f:
            mappings = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return pairs

    if not isinstance(mappings, list):
        return pairs

    for mapping in mappings:
        form_name = mapping.get("formName", "")
        form_type = mapping.get("formType", "")
        subject_type = mapping.get("subjectTypeUUID") or mapping.get("subjectType", "")
        program = mapping.get("programName", "")
        encounter = mapping.get("encounterTypeUUID") or mapping.get("encounterType", "")

        if not form_name or not form_type:
            continue

        user_msg = f"Create a form mapping for form '{form_name}' of type {form_type}"
        if subject_type:
            user_msg += f" for subject type {subject_type}"
        if program:
            user_msg += f" in program {program}"
        if encounter:
            user_msg += f" with encounter type {encounter}"

        pairs.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": json.dumps(mapping, indent=2)},
            ]
        })

    return pairs


def extract_knowledge_pairs(knowledge_dir: str) -> list[dict]:
    """Generate training pairs from knowledge base JSON/MD files."""
    pairs = []

    # Rule templates
    rule_templates_file = os.path.join(knowledge_dir, "rule_templates.json")
    if os.path.isfile(rule_templates_file):
        try:
            with open(rule_templates_file, "r") as f:
                templates = json.load(f)
            if isinstance(templates, list):
                for tmpl in templates:
                    name = tmpl.get("name", "")
                    desc = tmpl.get("description", "")
                    template = tmpl.get("template", "")
                    example = tmpl.get("example_filled", "")
                    if name and (template or example):
                        user_msg = f"Give me a template for: {name}. {desc}"
                        assistant_msg = example if example else template
                        pairs.append({
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": user_msg},
                                {"role": "assistant", "content": assistant_msg},
                            ]
                        })
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Bundle generation guide
    guide_file = os.path.join(knowledge_dir, "bundle_generation_guide.json")
    if os.path.isfile(guide_file):
        try:
            with open(guide_file, "r") as f:
                guide = json.load(f)
            if isinstance(guide, dict):
                for section, content in guide.items():
                    if isinstance(content, str) and len(content) > 50:
                        pairs.append({
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": f"Explain the Avni {section} in bundle generation"},
                                {"role": "assistant", "content": content},
                            ]
                        })
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    return pairs


def extract_db_export_pairs(db_export_dir: str) -> list[dict]:
    """Generate training pairs from production DB exports."""
    pairs = []
    knowledge_file = os.path.join(db_export_dir, "COMPLETE_KNOWLEDGE_BASE.md")
    if os.path.isfile(knowledge_file):
        with open(knowledge_file, "r") as f:
            content = f.read()

        # Split into sections and create Q&A pairs
        sections = re.split(r'###\s+\d+\.\s+', content)
        for section in sections[1:]:  # Skip header
            lines = section.strip().split("\n")
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
            if title and body and len(body) > 30:
                pairs.append({
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"What are the {title} in Avni?"},
                        {"role": "assistant", "content": body},
                    ]
                })

    return pairs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_bundle(bundle_dir: str) -> list[dict]:
    """Process a single implementation bundle directory."""
    all_pairs = []
    org_name = os.path.basename(bundle_dir)
    logger.info("Processing bundle: %s", org_name)

    # Concepts
    concepts_file = os.path.join(bundle_dir, "concepts.json")
    if os.path.isfile(concepts_file):
        pairs = extract_concept_pairs(concepts_file)
        logger.info("  concepts: %d pairs", len(pairs))
        all_pairs.extend(pairs)

    # Forms
    forms_dir = os.path.join(bundle_dir, "forms")
    if os.path.isdir(forms_dir):
        form_pairs = extract_form_pairs(forms_dir)
        logger.info("  forms: %d pairs", len(form_pairs))
        all_pairs.extend(form_pairs)

        rule_pairs = extract_rule_pairs(forms_dir)
        logger.info("  rules: %d pairs", len(rule_pairs))
        all_pairs.extend(rule_pairs)

    # Form mappings
    mapping_pairs = extract_form_mapping_pairs(bundle_dir)
    logger.info("  mappings: %d pairs", len(mapping_pairs))
    all_pairs.extend(mapping_pairs)

    return all_pairs


def main():
    parser = argparse.ArgumentParser(description="Prepare Avni fine-tuning training data")
    parser.add_argument("--bundles-dir", help="Directory containing implementation bundles")
    parser.add_argument("--knowledge-dir", default="app/knowledge/data/",
                        help="Knowledge base data directory")
    parser.add_argument("--db-export", help="Production DB export directory")
    parser.add_argument("--output-dir", default="training_data/",
                        help="Output directory for training JSONL files")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    all_pairs = []

    # 1. Process implementation bundles
    if args.bundles_dir and os.path.isdir(args.bundles_dir):
        for entry in sorted(os.listdir(args.bundles_dir)):
            bundle_path = os.path.join(args.bundles_dir, entry)
            if os.path.isdir(bundle_path):
                pairs = process_bundle(bundle_path)
                all_pairs.extend(pairs)

    # 2. Process knowledge base
    if os.path.isdir(args.knowledge_dir):
        kb_pairs = extract_knowledge_pairs(args.knowledge_dir)
        logger.info("Knowledge base: %d pairs", len(kb_pairs))
        all_pairs.extend(kb_pairs)

    # 3. Process DB exports
    if args.db_export and os.path.isdir(args.db_export):
        db_pairs = extract_db_export_pairs(args.db_export)
        logger.info("DB export: %d pairs", len(db_pairs))
        all_pairs.extend(db_pairs)

    # Deduplicate by user message
    seen = set()
    unique_pairs = []
    for pair in all_pairs:
        key = pair["messages"][1]["content"][:200]
        if key not in seen:
            seen.add(key)
            unique_pairs.append(pair)

    # Split into train (90%) and validation (10%)
    import random
    random.seed(42)
    random.shuffle(unique_pairs)
    split_idx = int(len(unique_pairs) * 0.9)
    train_pairs = unique_pairs[:split_idx]
    val_pairs = unique_pairs[split_idx:]

    # Write JSONL files
    train_file = os.path.join(args.output_dir, "avni_train.jsonl")
    val_file = os.path.join(args.output_dir, "avni_val.jsonl")

    with open(train_file, "w") as f:
        for pair in train_pairs:
            f.write(json.dumps(pair) + "\n")

    with open(val_file, "w") as f:
        for pair in val_pairs:
            f.write(json.dumps(pair) + "\n")

    logger.info("=" * 60)
    logger.info("Training data prepared:")
    logger.info("  Total unique pairs: %d", len(unique_pairs))
    logger.info("  Train: %d pairs -> %s", len(train_pairs), train_file)
    logger.info("  Validation: %d pairs -> %s", len(val_pairs), val_file)
    logger.info("=" * 60)

    # Write stats
    stats = {
        "total_pairs": len(unique_pairs),
        "train_pairs": len(train_pairs),
        "val_pairs": len(val_pairs),
        "sources": {
            "bundles": args.bundles_dir or "none",
            "knowledge": args.knowledge_dir,
            "db_export": args.db_export or "none",
        },
    }
    with open(os.path.join(args.output_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
