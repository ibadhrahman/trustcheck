# TrustCheck - Automated Windows PowerShell Setup Script
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  TrustCheck - Setup and Installation (Windows)       " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Check Python version
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[+] Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[!] Error: Python 3 is not found in PATH. Please install Python 3.11+." -ForegroundColor Red
    exit 1
}

# 2. Virtual environment setup
if (-Not (Test-Path ".venv")) {
    Write-Host "[*] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "[+] Existing virtual environment detected." -ForegroundColor Green
}

# 3. Upgrade pip and install dependencies
Write-Host "[*] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Dependency installation failed. Please inspect requirements." -ForegroundColor Red
    exit 1
}

# 4. Copy .env if not exists
if (-Not (Test-Path ".env")) {
    Write-Host "[*] Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "[+] Created .env file." -ForegroundColor Green
} else {
    Write-Host "[+] Existing .env file found." -ForegroundColor Green
}

# 5. Seed demo data
Write-Host "[*] Seeding demo database (seller accounts, products, sample orders)..." -ForegroundColor Yellow
& ".\.venv\Scripts\python.exe" scripts\seed_demo.py

Write-Host "======================================================" -ForegroundColor Green
Write-Host "  Setup completed successfully!                       " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host "To start TrustCheck:" -ForegroundColor White
Write-Host "  .\.venv\Scripts\uvicorn app.main:app --reload --port 8000" -ForegroundColor Cyan
Write-Host "Then visit http://localhost:8000 in your browser." -ForegroundColor White
