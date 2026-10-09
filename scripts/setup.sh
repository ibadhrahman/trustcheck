#!/usr/bin/env bash
# TrustCheck — Linux / macOS Setup Script
set -e

echo "======================================================"
echo "  TrustCheck — Setup & Installation (Linux/macOS)     "
echo "======================================================"

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "[-] Error: python3 is required but not installed."
    exit 1
fi
echo "[+] Found $(python3 --version)"

# 2. Virtual environment
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "[+] Existing virtual environment detected."
fi

source .venv/bin/activate

# 3. Dependencies
echo "[*] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Copy .env
if [ ! -f ".env" ]; then
    echo "[*] Creating .env from .env.example..."
    cp .env.example .env
    echo "[+] Created .env file."
fi

# 5. Seed database
echo "[*] Seeding demo database..."
python scripts/seed_demo.py

echo "======================================================"
echo "  Setup completed successfully!                       "
echo "======================================================"
echo "To start TrustCheck:"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload --port 8000"
echo "Then visit http://localhost:8000 in your browser."
