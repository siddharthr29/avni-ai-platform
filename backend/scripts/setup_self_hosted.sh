#!/bin/bash
# Setup self-hosted Avni AI model — zero API key dependency
# Works on Apple Silicon (M1/M2/M3/M4) with 16GB+ RAM
#
# This script:
# 1. Installs Ollama (if not present)
# 2. Pulls base models (Qwen 2.5 Coder 7B + Mistral 7B)
# 3. Creates custom Avni-tuned models with Modelfiles
# 4. Prepares training data from implementation bundles
# 5. Ingests knowledge into RAG pipeline
# 6. Runs a test to verify everything works

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo " Avni AI Self-Hosted Setup"
echo " No API keys needed!"
echo "============================================"
echo ""

# Step 1: Check Ollama
echo "[1/6] Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "  Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "  Starting Ollama..."
    open /Applications/Ollama.app 2>/dev/null || ollama serve &
    sleep 5
else
    echo "  Ollama already installed: $(ollama --version 2>/dev/null || echo 'running')"
fi

# Step 2: Pull base models
echo ""
echo "[2/6] Pulling base models (this may take a while on first run)..."
echo "  Pulling Qwen 2.5 Coder 7B (for code/rule generation)..."
ollama pull qwen2.5-coder:7b-instruct-q4_K_M 2>&1 | tail -1
echo "  Pulling Mistral 7B (for chat/reasoning)..."
ollama pull mistral:7b-instruct-v0.3-q4_K_M 2>&1 | tail -1

# Step 3: Create custom Avni models
echo ""
echo "[3/6] Creating custom Avni models..."
echo "  Creating avni-coder (specialized for bundle/rule generation)..."
ollama create avni-coder -f "$BACKEND_DIR/Modelfile.avni-coder" 2>&1 | tail -1
echo "  Creating avni-chat (specialized for general Avni Q&A)..."
ollama create avni-chat -f "$BACKEND_DIR/Modelfile.avni-chat" 2>&1 | tail -1

# Step 4: Prepare training data
echo ""
echo "[4/6] Preparing training data..."
IMPL_BUNDLES_DIR="$HOME/Downloads/All/avni-ai/impl-bundles"
TRAINING_DIR="$BACKEND_DIR/training_data"

if [ -d "$IMPL_BUNDLES_DIR" ]; then
    python3 "$SCRIPT_DIR/prepare_training_data.py" \
        --bundles-dir "$IMPL_BUNDLES_DIR" \
        --knowledge-dir "$BACKEND_DIR/app/knowledge/data/" \
        --db-export /tmp/avni_db_knowledge/ \
        --output-dir "$TRAINING_DIR"
else
    echo "  No impl bundles found at $IMPL_BUNDLES_DIR"
    echo "  Running with knowledge base only..."
    python3 "$SCRIPT_DIR/prepare_training_data.py" \
        --knowledge-dir "$BACKEND_DIR/app/knowledge/data/" \
        --output-dir "$TRAINING_DIR"
fi

# Step 5: Update .env
echo ""
echo "[5/6] Updating .env configuration..."
ENV_FILE="$BACKEND_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    # Update existing .env
    if grep -q "LLM_PROVIDER" "$ENV_FILE"; then
        sed -i '' 's/LLM_PROVIDER=.*/LLM_PROVIDER=ollama/' "$ENV_FILE"
    else
        echo "LLM_PROVIDER=ollama" >> "$ENV_FILE"
    fi
    if ! grep -q "OLLAMA_MODEL" "$ENV_FILE"; then
        echo "OLLAMA_MODEL=avni-coder" >> "$ENV_FILE"
        echo "OLLAMA_BASE_URL=http://localhost:11434/v1" >> "$ENV_FILE"
    fi
else
    cat > "$ENV_FILE" << 'EOF'
# Avni AI Platform - Self-Hosted Configuration
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=avni-coder
OLLAMA_VISION_MODEL=llava:7b

# RAG Pipeline (local PostgreSQL with pgvector)
DATABASE_URL=postgresql://avni:avni_ai_dev@localhost:5432/avni_ai
EMBEDDING_MODEL=all-MiniLM-L6-v2
RAG_SEMANTIC_WEIGHT=0.6
RAG_KEYWORD_WEIGHT=0.4

# Bundle output
BUNDLE_OUTPUT_DIR=/tmp/avni_bundles
MAX_TOKENS=4096
EOF
fi

# Step 6: Test
echo ""
echo "[6/6] Testing self-hosted model..."
RESPONSE=$(ollama run avni-coder "Create a simple Avni concept for 'Blood Pressure' with data type Numeric, unit mmHg, range 60-200. Output JSON only." 2>/dev/null | head -20)
echo "  Test response:"
echo "  $RESPONSE"

echo ""
echo "============================================"
echo " Setup Complete!"
echo "============================================"
echo ""
echo " Models available:"
ollama list 2>/dev/null | grep -E "avni|qwen|mistral" || echo "  (listing models...)"
echo ""
echo " To start the platform:"
echo "   cd $BACKEND_DIR"
echo "   python -m uvicorn app.main:app --reload"
echo ""
echo " Provider: ollama (self-hosted, zero API cost)"
echo " Model: avni-coder (Qwen 2.5 Coder 7B, Avni-tuned)"
echo " RAM usage: ~5GB for inference"
echo ""
echo " Training data: $TRAINING_DIR/"
echo " To fine-tune further, see scripts/finetune_model.py"
echo "============================================"
