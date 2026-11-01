@echo off
REM Menjalankan prototipe tanpa Docker (Windows). Prasyarat: Python 3.10+; Node.js 18+ (opsional).
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist analytics\out\metrics.json ( pushd analytics & python train_oulad.py & popd )
where npx >nul 2>nul
if %errorlevel%==0 if not "%USE_ETH_TESTER%"=="1" (
  pushd hardhat
  if not exist node_modules ( call npm install --no-audit --no-fund )
  start "Hardhat node" /min cmd /c "npx hardhat node --port 8545"
  popd
  set CHAIN_RPC=http://127.0.0.1:8545
  timeout /t 8 >nul
)
cd backend
echo Buka http://localhost:8000
uvicorn app:app --host 127.0.0.1 --port 8000
