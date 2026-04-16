#!/usr/bin/env bash
# run_opa_tests.sh
# Run OPA Rego unit tests and optionally connect OPA to the nautobot stack.
#
# Usage:
#   cd development/
#   bash run_opa_tests.sh
#
# Options (env vars):
#   KEEP_OPA=1        — leave OPA running after tests (useful for manual exploration)
#   ATTACH_NETWORK=1  — connect OPA to intent-networking_default so nautobot can
#                       reach opa:8181 (requires the main stack to be running first)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.opa.yml"
NAUTOBOT_NETWORK="intent-networking_default"

# ─────────────────────────────────────────────────────────────────────────────
# Teardown on exit (unless KEEP_OPA=1)
# ─────────────────────────────────────────────────────────────────────────────

cleanup() {
    if [[ "${KEEP_OPA:-0}" != "1" ]]; then
        echo ""
        echo "[ run_opa_tests ] Stopping OPA container..."
        docker compose -f "${COMPOSE_FILE}" down --remove-orphans
    else
        echo ""
        echo "[ run_opa_tests ] KEEP_OPA=1 — OPA container left running"
    fi
}
trap cleanup EXIT

# ─────────────────────────────────────────────────────────────────────────────
# Start OPA
# ─────────────────────────────────────────────────────────────────────────────

echo "[ run_opa_tests ] Starting OPA container..."
docker compose -f "${COMPOSE_FILE}" up -d --wait

# ─────────────────────────────────────────────────────────────────────────────
# Optionally attach to the nautobot network so nautobot→opa:8181 works
# ─────────────────────────────────────────────────────────────────────────────

if [[ "${ATTACH_NETWORK:-0}" == "1" ]]; then
    if docker network ls --format "{{.Name}}" | grep -q "^${NAUTOBOT_NETWORK}$"; then
        echo "[ run_opa_tests ] Connecting intent-opa to ${NAUTOBOT_NETWORK} (alias: opa)..."
        docker network connect --alias opa "${NAUTOBOT_NETWORK}" intent-opa 2>/dev/null || true
    else
        echo "[ run_opa_tests ] WARNING: ${NAUTOBOT_NETWORK} not found — is the main stack running?"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Run Rego unit tests
# ─────────────────────────────────────────────────────────────────────────────

echo "[ run_opa_tests ] Running Rego unit tests (--v0-compatible)..."
echo ""

docker run --rm \
    -v "${SCRIPT_DIR}/opa/policies:/policies:ro" \
    -v "${SCRIPT_DIR}/opa/tests:/tests:ro" \
    openpolicyagent/opa:latest \
    test /policies /tests --v0-compatible -v

echo ""
echo "[ run_opa_tests ] All tests passed."
    "$@"
