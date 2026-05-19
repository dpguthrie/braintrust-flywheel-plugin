#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

if [[ ! -f "${REPO_ROOT}/evals/bt-flywheel-docker/eval_subprocess.py" ]]; then
  echo "Could not find repo root from ${SCRIPT_DIR}" >&2
  exit 1
fi

cd "${REPO_ROOT}"

BT_ARGS=("--runner" "${BT_EVAL_RUNNER:-python3}")
if [[ "${UPLOAD:-0}" != "1" ]]; then
  BT_ARGS+=("--no-send-logs")
fi

echo "[bt-flywheel docker] running: bt eval ${BT_ARGS[*]} ${SCRIPT_DIR}/eval_subprocess.py"
exec bt eval "${BT_ARGS[@]}" "${SCRIPT_DIR}/eval_subprocess.py"
