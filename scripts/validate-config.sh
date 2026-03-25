#!/bin/bash
# Validates configuration consistency across the Avni AI Platform
set -e

ERRORS=0
WARNINGS=0
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Avni AI Platform Config Validation ==="
echo ""

# 1. Check Vite proxy port matches backend
echo "--- Vite Proxy Configuration ---"
PROXY_PORT=$(grep -oP "target:\s*'http://localhost:\K[0-9]+" "$ROOT_DIR/frontend/vite.config.ts" 2>/dev/null || echo "NOT_FOUND")
if [ "$PROXY_PORT" = "8080" ]; then
  echo "OK: Vite proxy targets localhost:$PROXY_PORT"
elif [ "$PROXY_PORT" = "NOT_FOUND" ]; then
  echo "ERROR: Could not find proxy target in vite.config.ts"
  ERRORS=$((ERRORS + 1))
else
  echo "ERROR: Vite proxy port ($PROXY_PORT) does not match expected backend port (8080)"
  ERRORS=$((ERRORS + 1))
fi
echo ""

# 2. Check .env exists
echo "--- Environment Files ---"
if [ -f "$ROOT_DIR/.env" ]; then
  echo "OK: .env file exists"
else
  echo "WARNING: .env file not found (copy from .env.example)"
  WARNINGS=$((WARNINGS + 1))
fi

if [ -f "$ROOT_DIR/.env.example" ]; then
  echo "OK: .env.example template exists"
else
  echo "WARNING: .env.example template not found"
  WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 3. Check required env vars (if .env exists)
echo "--- Required Environment Variables ---"
if [ -f "$ROOT_DIR/.env" ]; then
  for VAR in ANTHROPIC_API_KEY; do
    if grep -q "^${VAR}=" "$ROOT_DIR/.env" 2>/dev/null; then
      VALUE=$(grep "^${VAR}=" "$ROOT_DIR/.env" | cut -d'=' -f2-)
      if [ -z "$VALUE" ] || [ "$VALUE" = "your-key-here" ]; then
        echo "WARNING: $VAR is set but appears to be a placeholder"
        WARNINGS=$((WARNINGS + 1))
      else
        echo "OK: $VAR is configured"
      fi
    else
      echo "WARNING: $VAR not found in .env"
      WARNINGS=$((WARNINGS + 1))
    fi
  done
else
  echo "SKIP: No .env file to validate"
fi
echo ""

# 4. Check Docker Compose validity
echo "--- Docker Compose ---"
if [ -f "$ROOT_DIR/docker-compose.yml" ]; then
  if command -v docker &>/dev/null; then
    if docker compose -f "$ROOT_DIR/docker-compose.yml" config --quiet 2>/dev/null; then
      echo "OK: docker-compose.yml is valid"
    else
      echo "ERROR: docker-compose.yml has configuration errors"
      ERRORS=$((ERRORS + 1))
    fi
  else
    echo "SKIP: Docker not installed, cannot validate docker-compose.yml"
  fi
else
  echo "SKIP: No docker-compose.yml found"
fi
echo ""

# 5. Check for secrets in source code
echo "--- Secret Scanning ---"
SECRETS_FOUND=0
if grep -rn "sk-proj-\|sk-ant-" "$ROOT_DIR/frontend/src/" --include="*.ts" --include="*.tsx" 2>/dev/null; then
  echo "ERROR: API keys found in frontend source code"
  SECRETS_FOUND=1
  ERRORS=$((ERRORS + 1))
fi
if grep -rn "sk-proj-\|sk-ant-" "$ROOT_DIR/backend/app/" --include="*.py" 2>/dev/null; then
  echo "ERROR: API keys found in backend source code"
  SECRETS_FOUND=1
  ERRORS=$((ERRORS + 1))
fi
if [ "$SECRETS_FOUND" -eq 0 ]; then
  echo "OK: No hardcoded secrets found in source code"
fi
echo ""

# 6. Check backend dependencies file
echo "--- Dependency Files ---"
if [ -f "$ROOT_DIR/backend/requirements.txt" ]; then
  DEP_COUNT=$(wc -l < "$ROOT_DIR/backend/requirements.txt" | tr -d ' ')
  echo "OK: backend/requirements.txt ($DEP_COUNT dependencies)"
else
  echo "ERROR: backend/requirements.txt not found"
  ERRORS=$((ERRORS + 1))
fi

if [ -f "$ROOT_DIR/frontend/package.json" ]; then
  echo "OK: frontend/package.json exists"
else
  echo "ERROR: frontend/package.json not found"
  ERRORS=$((ERRORS + 1))
fi
echo ""

# Summary
echo "=== Validation Summary ==="
echo "Errors:   $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [ "$ERRORS" -gt 0 ]; then
  echo "FAILED: $ERRORS error(s) found. Fix before proceeding."
  exit 1
else
  echo "PASSED: Configuration is valid."
  exit 0
fi
