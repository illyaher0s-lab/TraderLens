#!/usr/bin/env bash
set -euo pipefail

# Real API smoke test runner template.
# Set secrets in your local shell before running this script.
# Do not write real API keys or tokens into this file.

export RUN_REAL_API_SMOKE="1"
export RESEARCH_LLM_BASE_URL="${RESEARCH_LLM_BASE_URL:-https://cc-vibe.com}"
export RESEARCH_LLM_MODEL="${RESEARCH_LLM_MODEL:-claude-sonnet-4-6}"

: "${TUSHARE_TOKEN:?TUSHARE_TOKEN is required; set it locally, do not commit it.}"
: "${RESEARCH_LLM_API_KEY:?RESEARCH_LLM_API_KEY is required; set it locally, do not commit it.}"

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy

echo "Running real API smoke tests with local environment variables."
echo "TUSHARE_API_URL=${TUSHARE_API_URL:-}"
echo "RESEARCH_LLM_BASE_URL=$RESEARCH_LLM_BASE_URL"
echo "RESEARCH_LLM_MODEL=$RESEARCH_LLM_MODEL"

.venv/Scripts/python.exe -m pytest tests/test_v1_real_api_smoke.py -v -s
