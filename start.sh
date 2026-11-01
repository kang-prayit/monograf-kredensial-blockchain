#!/usr/bin/env bash
# Menjalankan prototipe tanpa Docker (Linux/macOS).
# Mode default: blockchain Hardhat lokal bila Node.js tersedia; jika tidak, eth-tester dalam proses.
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
[ -d .venv ] || $PY -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
if [ ! -f analytics/out/metrics.json ]; then (cd analytics && python train_oulad.py) ; fi
if command -v npx >/dev/null 2>&1 && [ "${USE_ETH_TESTER:-0}" != "1" ]; then
  (cd hardhat && [ -d node_modules ] || npm install --no-audit --no-fund)
  (cd hardhat && nohup npx hardhat node --port 8545 > ../data_hardhat.log 2>&1 &)
  export CHAIN_RPC=http://127.0.0.1:8545
  sleep 6
fi
cd backend
echo "Buka http://localhost:8000"
exec uvicorn app:app --host 127.0.0.1 --port 8000
