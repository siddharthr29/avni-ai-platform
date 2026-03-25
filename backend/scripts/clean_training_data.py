#!/usr/bin/env python3
"""Clean and enrich training data for quality fine-tuning.

Takes raw extracted training data and:
1. Removes duplicates and low-quality pairs
2. Normalizes SRS data types to Avni types
3. Enriches SRS field pairs with proper Avni concept JSON responses
4. Filters out empty/malformed entries
5. Balances the dataset across different task types
6. Merges bundle + SRS training data into a single clean dataset

Usage:
    python scripts/clean_training_data.py \
        --input-dir training_data/ \
        --output-dir training_data/clean/
"""

import argparse
import json
import logging
import os
import re
import sys
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("clean_data")

# SRS data type → Avni concept type mapping
SRS_TO_AVNI_TYPE = {
    "text": "Text",
    "short text": "Text",
    "long text": "Notes",
    "notes": "Notes",
    "number": "Numeric",
    "numeric": "Numeric",
    "integer": "Numeric",
    "decimal": "Numeric",
    "date": "Date",
    "calender": "Date",
    "calendar": "Date",
    "datetime": "DateTime",
    "time": "Time",
    "single select": "Coded",
    "multi select": "Coded",
    "multiselect": "Coded",
    "singleselect": "Coded",
    "dropdown": "Coded",
    "coded": "Coded",
    "pre added options": "Coded",
    "pre-added options": "Coded",
    "image": "Image",
    "photo": "Image",
    "file": "File",
    "video": "Video",
    "audio": "Audio",
    "phone number": "PhoneNumber",
    "phonenumber": "PhoneNumber",
    "phone": "PhoneNumber",
    "location": "Location",
    "id": "Id",
    "question group": "QuestionGroup",
    "auto calculated": "Numeric",
    "yes/no": "Coded",
    "y/n": "Coded",
    "boolean": "Coded",
}

SYSTEM_PROMPT = (
    "You are the Avni Platform Architect. Generate exact Avni bundle JSON, "
    "JavaScript rules, and declarative rules. Use provided concept names and UUIDs. "
    "Output only code, no explanations unless asked."
)


def clean_text(text: str) -> str:
    """Clean text of common artifacts."""
    if not text:
        return ""
    # Remove null/None strings
    text = re.sub(r'\b(None|null|nan|NaN|N/A)\b', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove leading/trailing pipes
    text = text.strip('| ')
    return text


def normalize_data_type(raw_type: str) -> str:
    """Normalize SRS data type string to Avni concept type."""
    if not raw_type:
        return ""
    cleaned = raw_type.strip().lower()
    return SRS_TO_AVNI_TYPE.get(cleaned, "")


def enrich_srs_field_pair(pair: dict) -> dict | None:
    """Enrich an SRS field training pair with proper Avni concept JSON response."""
    messages = pair.get("messages", [])
    if len(messages) < 3:
        return None

    user_msg = messages[1].get("content", "")
    assistant_msg = messages[2].get("content", "")

    # Extract field info from the assistant message (raw SRS format)
    field_name = ""
    data_type = ""
    options = ""
    mandatory = False

    for line in assistant_msg.split("\n"):
        line = line.strip()
        if line.startswith("Field:"):
            field_name = line.replace("Field:", "").strip()
        elif line.startswith("Data Type:"):
            data_type = line.replace("Data Type:", "").strip()
        elif line.startswith("Options:"):
            options = line.replace("Options:", "").strip()
        elif line.startswith("Mandatory:"):
            mandatory = line.replace("Mandatory:", "").strip().lower() in ("yes", "true", "y")

    if not field_name:
        return None

    # Normalize data type
    avni_type = normalize_data_type(data_type)
    if not avni_type:
        return None

    # Build proper Avni concept JSON
    concept = {
        "name": field_name,
        "uuid": str(uuid.uuid4()),
        "dataType": avni_type,
        "active": True,
    }

    if avni_type == "Coded" and options:
        # Parse options
        answers = []
        # Try comma-separated, pipe-separated, or newline-separated
        option_list = re.split(r'[,\n|]', options)
        for i, opt in enumerate(option_list):
            opt = clean_text(opt)
            if opt and len(opt) > 1:
                answers.append({
                    "name": opt,
                    "uuid": str(uuid.uuid4()),
                    "order": float(i),
                })
        if answers:
            concept["answers"] = answers

    # Create enriched user message
    enriched_user = f"Create an Avni concept for '{field_name}' with data type {avni_type}"
    if avni_type == "Coded" and concept.get("answers"):
        answer_names = [a["name"] for a in concept["answers"]]
        enriched_user += f" with answers: {', '.join(answer_names)}"
    if mandatory:
        enriched_user += " (mandatory)"

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": enriched_user},
            {"role": "assistant", "content": json.dumps(concept, indent=2)},
        ]
    }


def is_valid_pair(pair: dict) -> bool:
    """Check if a training pair is valid and useful."""
    messages = pair.get("messages", [])
    if len(messages) < 3:
        return False

    user_msg = messages[1].get("content", "")
    assistant_msg = messages[2].get("content", "")

    # Skip empty messages
    if not user_msg or not assistant_msg:
        return False

    # Skip very short responses (likely garbage)
    if len(assistant_msg) < 10:
        return False

    # Skip if user message is too short to be useful
    if len(user_msg) < 15:
        return False

    # Skip if assistant message contains common garbage patterns
    garbage_patterns = ["None", "nan", "NaN", "undefined", "#REF!", "#VALUE!", "#N/A"]
    for pattern in garbage_patterns:
        if assistant_msg.strip() == pattern:
            return False

    return True


def categorize_pair(pair: dict) -> str:
    """Categorize a training pair by task type."""
    user_msg = pair["messages"][1]["content"].lower()
    assistant_msg = pair["messages"][2]["content"].lower()

    # Check rules first (most specific)
    if any(kw in user_msg for kw in ["rule", "skip logic", "viewfilter", "declarative rule"]):
        return "rule"
    if any(kw in assistant_msg for kw in [
        "statusbuilder", "formelementstatusbuilder", "showformelement",
        "actiontype", "compoundrule", "visitschedulebuilder",
    ]):
        return "rule"

    # Form mappings
    if any(kw in user_msg for kw in ["form mapping", "formmapping"]):
        return "mapping"

    # Forms (but not form mappings)
    if any(kw in user_msg for kw in ["form called", "form '", "formtype", "formelementgroup"]):
        return "form"
    if "formelementgroups" in assistant_msg:
        return "form"

    # Concepts
    if any(kw in user_msg for kw in ["concept for", "data type", "create an avni concept"]):
        return "concept"

    # SRS
    if any(kw in user_msg for kw in ["srs", "scoping"]):
        return "srs"

    return "other"


def main():
    parser = argparse.ArgumentParser(description="Clean and enrich training data")
    parser.add_argument("--input-dir", default="training_data/")
    parser.add_argument("--output-dir", default="training_data/clean/")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    all_pairs = []
    stats = {"loaded": 0, "enriched": 0, "filtered": 0, "final": 0}

    # Load bundle training data
    bundle_train = os.path.join(args.input_dir, "avni_train.jsonl")
    if os.path.isfile(bundle_train):
        with open(bundle_train, "r") as f:
            for line in f:
                try:
                    pair = json.loads(line.strip())
                    all_pairs.append(pair)
                    stats["loaded"] += 1
                except json.JSONDecodeError:
                    pass
        logger.info("Loaded %d bundle training pairs", stats["loaded"])

    bundle_val = os.path.join(args.input_dir, "avni_val.jsonl")
    if os.path.isfile(bundle_val):
        with open(bundle_val, "r") as f:
            for line in f:
                try:
                    pair = json.loads(line.strip())
                    all_pairs.append(pair)
                    stats["loaded"] += 1
                except json.JSONDecodeError:
                    pass

    # Load and enrich SRS training data
    srs_train = os.path.join(args.input_dir, "avni_srs_train.jsonl")
    if os.path.isfile(srs_train):
        srs_count = 0
        enriched_count = 0
        with open(srs_train, "r") as f:
            for line in f:
                try:
                    pair = json.loads(line.strip())
                    srs_count += 1

                    # Enrich SRS pairs with proper Avni JSON responses
                    enriched = enrich_srs_field_pair(pair)
                    if enriched:
                        all_pairs.append(enriched)
                        enriched_count += 1
                        stats["enriched"] += 1
                    else:
                        # Keep original if enrichment fails
                        all_pairs.append(pair)
                except json.JSONDecodeError:
                    pass
        logger.info("Loaded %d SRS pairs, enriched %d", srs_count, enriched_count)

    # Filter invalid pairs
    valid_pairs = [p for p in all_pairs if is_valid_pair(p)]
    stats["filtered"] = len(all_pairs) - len(valid_pairs)
    logger.info("Filtered %d invalid pairs", stats["filtered"])

    # Deduplicate by user message (first 200 chars)
    seen = set()
    unique_pairs = []
    for pair in valid_pairs:
        key = pair["messages"][1]["content"][:200]
        if key not in seen:
            seen.add(key)
            unique_pairs.append(pair)
    logger.info("Deduplicated: %d -> %d pairs", len(valid_pairs), len(unique_pairs))

    # Categorize and balance
    categories = {}
    for pair in unique_pairs:
        cat = categorize_pair(pair)
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(pair)

    logger.info("Category distribution:")
    for cat, pairs in sorted(categories.items()):
        logger.info("  %s: %d pairs", cat, len(pairs))

    # Balance: cap overrepresented categories at 5000
    MAX_PER_CATEGORY = 5000
    balanced_pairs = []
    for cat, pairs in categories.items():
        if len(pairs) > MAX_PER_CATEGORY:
            import random
            random.seed(42)
            balanced_pairs.extend(random.sample(pairs, MAX_PER_CATEGORY))
            logger.info("  Capped %s from %d to %d", cat, len(pairs), MAX_PER_CATEGORY)
        else:
            balanced_pairs.extend(pairs)

    # Shuffle
    import random
    random.seed(42)
    random.shuffle(balanced_pairs)

    # Split 90/10
    split_idx = int(len(balanced_pairs) * 0.9)
    train_pairs = balanced_pairs[:split_idx]
    val_pairs = balanced_pairs[split_idx:]

    stats["final"] = len(balanced_pairs)

    # Write clean output
    train_file = os.path.join(args.output_dir, "avni_train_clean.jsonl")
    val_file = os.path.join(args.output_dir, "avni_val_clean.jsonl")

    with open(train_file, "w") as f:
        for pair in train_pairs:
            f.write(json.dumps(pair) + "\n")

    with open(val_file, "w") as f:
        for pair in val_pairs:
            f.write(json.dumps(pair) + "\n")

    # Write stats
    with open(os.path.join(args.output_dir, "cleaning_stats.json"), "w") as f:
        json.dump({
            "loaded": stats["loaded"],
            "srs_enriched": stats["enriched"],
            "filtered_invalid": stats["filtered"],
            "deduplicated": len(valid_pairs) - len(unique_pairs),
            "final_train": len(train_pairs),
            "final_val": len(val_pairs),
            "categories": {cat: len(pairs) for cat, pairs in categories.items()},
        }, f, indent=2)

    logger.info("=" * 60)
    logger.info("Cleaning complete:")
    logger.info("  Input: %d raw pairs", stats["loaded"] + stats["enriched"])
    logger.info("  Output: %d clean pairs (%d train + %d val)",
                len(balanced_pairs), len(train_pairs), len(val_pairs))
    logger.info("  Train: %s", train_file)
    logger.info("  Val: %s", val_file)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
