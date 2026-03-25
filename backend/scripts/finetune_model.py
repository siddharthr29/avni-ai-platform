#!/usr/bin/env python3
"""Fine-tune the Avni model using Unsloth (4x faster LoRA on Apple Silicon).

This script fine-tunes a base model (Qwen 2.5 Coder 7B) on Avni-specific
training data using LoRA adapters. The resulting model can be exported
to GGUF format and loaded into Ollama.

Requirements:
    pip install unsloth datasets trl

Usage:
    # Quick fine-tune (recommended for M3 16GB)
    python scripts/finetune_model.py \
        --train-file training_data/avni_train.jsonl \
        --val-file training_data/avni_val.jsonl \
        --output-dir models/avni-coder-finetuned \
        --epochs 3 \
        --batch-size 1

    # After fine-tuning, convert to GGUF and load into Ollama:
    # python scripts/finetune_model.py --export-gguf models/avni-coder-finetuned
    # ollama create avni-coder-ft -f models/avni-coder-finetuned/Modelfile
"""

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("finetune")


def load_training_data(train_file: str, val_file: str | None = None):
    """Load JSONL training data into HuggingFace datasets."""
    from datasets import Dataset

    train_data = []
    with open(train_file, "r") as f:
        for line in f:
            item = json.loads(line.strip())
            # Convert to chat format string for training
            messages = item["messages"]
            text = ""
            for msg in messages:
                if msg["role"] == "system":
                    text += f"<|system|>\n{msg['content']}\n"
                elif msg["role"] == "user":
                    text += f"<|user|>\n{msg['content']}\n"
                elif msg["role"] == "assistant":
                    text += f"<|assistant|>\n{msg['content']}\n"
            train_data.append({"text": text})

    train_dataset = Dataset.from_list(train_data)

    val_dataset = None
    if val_file and os.path.isfile(val_file):
        val_data = []
        with open(val_file, "r") as f:
            for line in f:
                item = json.loads(line.strip())
                messages = item["messages"]
                text = ""
                for msg in messages:
                    if msg["role"] == "system":
                        text += f"<|system|>\n{msg['content']}\n"
                    elif msg["role"] == "user":
                        text += f"<|user|>\n{msg['content']}\n"
                    elif msg["role"] == "assistant":
                        text += f"<|assistant|>\n{msg['content']}\n"
                val_data.append({"text": text})
        val_dataset = Dataset.from_list(val_data)

    return train_dataset, val_dataset


def finetune(args):
    """Run LoRA fine-tuning with Unsloth."""
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        logger.error(
            "Unsloth not installed. Install with:\n"
            "  pip install unsloth\n"
            "Or use the alternative MLX fine-tuning (for Apple Silicon):\n"
            "  pip install mlx-lm\n"
        )
        sys.exit(1)

    from trl import SFTTrainer
    from transformers import TrainingArguments

    logger.info("Loading base model: %s", args.base_model)

    # Load model with 4-bit quantization for memory efficiency
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        dtype=None,  # Auto-detect
        load_in_4bit=True,
    )

    # Add LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,  # LoRA rank
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    logger.info("Loading training data...")
    train_dataset, val_dataset = load_training_data(args.train_file, args.val_file)
    logger.info("Train: %d examples, Val: %d examples",
                len(train_dataset), len(val_dataset) if val_dataset else 0)

    # Training arguments optimized for M3 16GB
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        warmup_steps=50,
        logging_steps=10,
        save_steps=500,
        save_total_limit=2,
        fp16=False,
        bf16=True,  # Apple Silicon supports bf16
        optim="adamw_8bit",
        seed=42,
        report_to="none",
        eval_strategy="steps" if val_dataset else "no",
        eval_steps=100 if val_dataset else None,
        load_best_model_at_end=bool(val_dataset),
        metric_for_best_model="eval_loss" if val_dataset else None,
        greater_is_better=False,
    )

    # Early stopping callback
    callbacks = []
    if val_dataset and args.early_stopping_patience > 0:
        from transformers import EarlyStoppingCallback
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience))

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        packing=True,  # Pack multiple examples per sequence
        args=training_args,
        callbacks=callbacks,
    )

    logger.info("Starting fine-tuning...")
    trainer.train()

    logger.info("Saving model to %s", args.output_dir)
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    logger.info("Fine-tuning complete!")
    logger.info("To export to GGUF for Ollama:")
    logger.info("  python scripts/finetune_model.py --export-gguf %s", args.output_dir)


def export_gguf(model_dir: str):
    """Export fine-tuned model to GGUF format for Ollama."""
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        logger.error("Unsloth not installed. pip install unsloth")
        sys.exit(1)

    logger.info("Loading fine-tuned model from %s", model_dir)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_dir,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
    )

    gguf_path = os.path.join(model_dir, "avni-coder-ft.gguf")
    logger.info("Exporting to GGUF: %s", gguf_path)

    model.save_pretrained_gguf(
        model_dir,
        tokenizer,
        quantization_method="q4_k_m",
    )

    # Create Modelfile for Ollama
    modelfile_path = os.path.join(model_dir, "Modelfile")
    with open(modelfile_path, "w") as f:
        f.write(f"FROM {gguf_path}\n\n")
        f.write("PARAMETER temperature 0.1\n")
        f.write("PARAMETER top_p 0.9\n")
        f.write("PARAMETER num_predict 4096\n")
        f.write("PARAMETER num_ctx 8192\n\n")
        f.write('SYSTEM """You are the Avni Platform Architect. Generate exact Avni bundle JSON, ')
        f.write("JavaScript rules, and declarative rules. Use provided concept names and UUIDs. ")
        f.write('Output only code, no explanations unless asked."""\n')

    logger.info("GGUF export complete!")
    logger.info("To load into Ollama:")
    logger.info("  ollama create avni-coder-ft -f %s", modelfile_path)


def _dry_run(args):
    """Validate data and report stats without training."""
    train_dataset, val_dataset = load_training_data(args.train_file, args.val_file)
    logger.info("=== DRY RUN ===")
    logger.info("Train file: %s (%d examples)", args.train_file, len(train_dataset))
    if val_dataset:
        logger.info("Val file: %s (%d examples)", args.val_file, len(val_dataset))

    # Compute text length stats
    train_lengths = [len(t["text"]) for t in train_dataset]
    logger.info("Train text lengths: min=%d, max=%d, avg=%d, median=%d",
                min(train_lengths), max(train_lengths),
                sum(train_lengths) // len(train_lengths),
                sorted(train_lengths)[len(train_lengths) // 2])

    # Check for truncation at max_seq_length
    approx_tokens = [l // 4 for l in train_lengths]  # rough char-to-token ratio
    truncated = sum(1 for t in approx_tokens if t > args.max_seq_length)
    logger.info("Estimated examples exceeding max_seq_length (%d): %d (%.1f%%)",
                args.max_seq_length, truncated, truncated / len(train_lengths) * 100)

    logger.info("Base model: %s", args.base_model)
    logger.info("Config: epochs=%d, batch_size=%d, lr=%s, max_seq=%d",
                args.epochs, args.batch_size, args.learning_rate, args.max_seq_length)
    logger.info("Dry run complete — data is valid.")


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Avni model")
    parser.add_argument("--train-file", default="training_data/avni_train.jsonl")
    parser.add_argument("--val-file", default="training_data/avni_val.jsonl")
    parser.add_argument("--output-dir", default="models/avni-coder-finetuned")
    parser.add_argument("--base-model", default="unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--early-stopping-patience", type=int, default=3,
                        help="Stop training if val loss doesn't improve for N evals")
    parser.add_argument("--export-gguf", metavar="MODEL_DIR",
                        help="Export a fine-tuned model to GGUF format")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate data and report stats without training")
    args = parser.parse_args()

    if args.export_gguf:
        export_gguf(args.export_gguf)
    elif args.dry_run:
        _dry_run(args)
    else:
        finetune(args)


if __name__ == "__main__":
    main()
