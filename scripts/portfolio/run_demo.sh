#!/usr/bin/env bash
# Insurance Agent — Portfolio Demo Runner
#
# Usage: ./scripts/portfolio/run_demo.sh
#
# Runs the REAL system: environment check → Demo A (normal decision)
# → Demo B (evidence tampering → DENY) → Demo C (insufficient
# evidence → ABSTAIN). No faked results.
#
# For LIVE WeKnora mode, set:
#   INSURANCE_AGENT_KNOWLEDGE_PROVIDER=weknora
#   INSURANCE_AGENT_WEKNORA_URL=http://127.0.0.1:8080
#   INSURANCE_AGENT_WEKNORA_API_KEY=<key>
#   INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID=<kb-id>
#   INSURANCE_AGENT_KNOWLEDGE_REGISTRY=<projection.json>

set -e
cd "$(dirname "$0")/../.."

echo "================================"
echo "Insurance Agent Portfolio Demo"
echo "================================"
echo ""

# 1. Environment check
echo "[1] Environment"
if command -v python &>/dev/null; then
    PY=python
elif command -v python3 &>/dev/null; then
    PY=python3
else
    echo "    Python: NOT FOUND"
    exit 1
fi
echo "    Python: $($PY --version 2>&1)"

if [ -n "$INSURANCE_AGENT_WEKNORA_URL" ]; then
    echo "    WeKnora: $INSURANCE_AGENT_WEKNORA_URL (live mode)"
    if curl -s -o /dev/null -w '%{http_code}' \
        "$INSURANCE_AGENT_WEKNORA_URL/health" 2>/dev/null | \
        grep -q "200"; then
        echo "    WeKnora health: PASS"
    else
        echo "    WeKnora health: UNREACHABLE (will fail closed)"
    fi
else
    echo "    WeKnora: not configured (offline deterministic mode)"
fi
echo ""

# 2-4. Run the three demos
$PY demo/portfolio_demo/run_all.py
DEMO_EXIT=$?

echo ""
if [ $DEMO_EXIT -eq 0 ]; then
    echo "================================"
    echo "PORTFOLIO DEMO COMPLETE"
    echo "================================"
else
    echo "================================"
    echo "PORTFOLIO DEMO — FAILURES PRESENT"
    echo "================================"
fi
exit $DEMO_EXIT
