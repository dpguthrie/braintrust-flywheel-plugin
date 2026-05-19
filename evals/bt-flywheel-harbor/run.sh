#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_DIR="${BT_FLYWHEEL_EVAL_VENV:-${SCRIPT_DIR}/.venv}"
PYTHON_BIN="${PYTHON:-python3}"
SUITE_CONFIG="${BT_FLYWHEEL_SUITE_CONFIG:-${BT_FLYWHEEL_MATRIX_CONFIG:-${SCRIPT_DIR}/suite.toml}}"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
REQUIREMENTS_HASH_FILE="${VENV_DIR}/.requirements.sha256"

cd "${REPO_ROOT}"
PATH="${HOME}/.local/bin:${PATH}"
export PATH

if [[ "${BT_FLYWHEEL_LOAD_ENV:-1}" == "1" && -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi

if [[ "${SKIP_PYTHON_INSTALL:-0}" != "1" ]]; then
  created_venv=0
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[bt-flywheel harbor] creating Python venv: ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    created_venv=1
  fi
  requirements_hash="$("${VENV_DIR}/bin/python" -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "${REQUIREMENTS_FILE}")"
  current_hash="$(cat "${REQUIREMENTS_HASH_FILE}" 2>/dev/null || true)"
  if [[ "${FORCE_PYTHON_INSTALL:-0}" == "1" || "${created_venv}" == "1" || "${requirements_hash}" != "${current_hash}" ]]; then
    echo "[bt-flywheel harbor] installing Python requirements from ${REQUIREMENTS_FILE}"
    if command -v uv >/dev/null 2>&1; then
      uv pip install --python "${VENV_DIR}/bin/python" -r "${REQUIREMENTS_FILE}"
    else
      "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --upgrade pip
      "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check -r "${REQUIREMENTS_FILE}"
    fi
    printf "%s\n" "${requirements_hash}" > "${REQUIREMENTS_HASH_FILE}"
  fi
fi

if [[ -d "${VENV_DIR}/bin" ]]; then
  PATH="${VENV_DIR}/bin:${PATH}"
  export PATH
fi

if ! command -v harbor >/dev/null 2>&1; then
  echo "Harbor is required and should be installed from ${REQUIREMENTS_FILE}." >&2
  echo "Unset SKIP_PYTHON_INSTALL or install it with: uv pip install --python \"${VENV_DIR}/bin/python\" harbor" >&2
  exit 127
fi

PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONPATH
export BT_FLYWHEEL_SUITE_CONFIG="${SUITE_CONFIG}"
HARBOR_MAX_CONCURRENCY="${HARBOR_MAX_CONCURRENCY:-4}"
export HARBOR_MAX_CONCURRENCY

BT_RUNNER="${BT_EVAL_PYTHON_RUNNER:-}"
if [[ -z "${BT_RUNNER}" && -x "${VENV_DIR}/bin/python" ]]; then
  BT_RUNNER="${VENV_DIR}/bin/python"
fi
DIRECT_PYTHON="${BT_RUNNER:-${PYTHON_BIN}}"

echo "[bt-flywheel harbor] launching runner with ${DIRECT_PYTHON}"
exec "${DIRECT_PYTHON}" evals/bt-flywheel-harbor/run_harbor_batch.py
