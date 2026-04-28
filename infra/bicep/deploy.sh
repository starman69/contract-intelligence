#!/usr/bin/env bash
# Thin wrapper around `az deployment sub create`.
# Usage: ./deploy.sh [env]   (default: dev)
# Prereqs: az login + az account set --subscription <id>

set -euo pipefail

ENV="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARAM_FILE="${SCRIPT_DIR}/env/${ENV}.bicepparam"
TEMPLATE="${SCRIPT_DIR}/main.bicep"

if [[ ! -f "${PARAM_FILE}" ]]; then
  echo "Error: parameter file not found at ${PARAM_FILE}" >&2
  exit 1
fi

LOCATION="$(awk -F"'" '/^param location/ {print $2}' "${PARAM_FILE}")"
LOCATION="${LOCATION:-eastus2}"

DEPLOYMENT_NAME="contracts-poc-${ENV}-$(date +%Y%m%d%H%M%S)"

echo "→ what-if (read-only preview)"
az deployment sub what-if \
  --name "${DEPLOYMENT_NAME}" \
  --location "${LOCATION}" \
  --template-file "${TEMPLATE}" \
  --parameters "${PARAM_FILE}"

read -r -p "Proceed with deployment? [y/N] " confirm
if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

echo "→ deploying"
az deployment sub create \
  --name "${DEPLOYMENT_NAME}" \
  --location "${LOCATION}" \
  --template-file "${TEMPLATE}" \
  --parameters "${PARAM_FILE}"

echo "→ outputs"
az deployment sub show \
  --name "${DEPLOYMENT_NAME}" \
  --query properties.outputs \
  -o json
