#!/usr/bin/env pwsh
# ═══════════════════════════════════════════════════════════════
# CARMA Backend — Quick Setup Script (Windows PowerShell)
# ═══════════════════════════════════════════════════════════════

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

Write-Host "`n[CARMA] Starting backend setup..." -ForegroundColor Cyan

# 1. Check Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[ERROR] Python not found. Install Python 3.11+ first." -ForegroundColor Red; exit 1
}
Write-Host "[OK] Python: $(python --version)" -ForegroundColor Green

# 2. Create virtual environment
if (-not (Test-Path ".\venv")) {
    Write-Host "[CARMA] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}
Write-Host "[OK] Virtualenv ready." -ForegroundColor Green

# 3. Install dependencies
Write-Host "[CARMA] Installing dependencies (this may take a few minutes)..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt

$installExtras = Read-Host "Install the optional analysis extras (statsmodels, declare4py)? [y/N]"
if ($installExtras -match '^[yY]') {
    & ".\venv\Scripts\python.exe" -m pip install -r requirements-optional.txt
}

# 4. Create .env if missing
if (-not (Test-Path ".\.env")) {
    Copy-Item ".\.env.example" ".\.env"
    Write-Host "[OK] .env created from template. Edit DB credentials if needed." -ForegroundColor Yellow
}

# 5. Decide which database to use
#    - SQLite (config.settings_sqlite) needs nothing extra — good for a first run.
#    - PostgreSQL (config.settings) is used for the actual study.
$usePostgres = $false
if (Get-Command psql -ErrorAction SilentlyContinue) {
    $usePostgres = $true
}
if ($usePostgres) {
    $settingsModule = "config.settings"
    Write-Host "[CARMA] Using PostgreSQL (config.settings)." -ForegroundColor Yellow
} else {
    $settingsModule = "config.settings_sqlite"
    Write-Host "[CARMA] psql not found — using SQLite (config.settings_sqlite)." -ForegroundColor Yellow
}
$env:DJANGO_SETTINGS_MODULE = $settingsModule

# 6. Run Django migrations
Write-Host "`n[CARMA] Running migrations..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" manage.py migrate

# 7. Seed the B0-B7 experiment configurations
Write-Host "`n[CARMA] Seeding experiment configurations B0-B7..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" manage.py seed_configurations

# 8. Load benchmark scenarios S0-S6
Write-Host "`n[CARMA] Loading benchmark scenarios S0-S6..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" manage.py shell -c @"
from apps.benchmark.models import BenchmarkScenario
scenarios = [
    ('S0','Nominal',           'Standard case, no perturbation.'),
    ('S1','Exception',         'Unexpected event disrupts the running case.'),
    ('S2','Rule Change',       'A constraint or policy changes mid-execution.'),
    ('S3','Structural Drift',  'Process model structure has drifted from the log.'),
    ('S4','Ambiguous Input',   'Perturbation event is underspecified or vague.'),
    ('S5','Conflicting Intents','Two agents or users request incompatible adaptations.'),
    ('S6','Adversarial',       'Intentionally misleading or adversarial input.'),
]
for code, name, desc in scenarios:
    BenchmarkScenario.objects.get_or_create(code=code, defaults={'name':name,'description':desc})
print('Scenarios seeded.')
"@

# 9. Create the superuser with a RANDOM password (never a hardcoded default)
Write-Host "`n[CARMA] Creating admin superuser..." -ForegroundColor Yellow
$adminEmail = "admin@carma.local"
if (& ".\venv\Scripts\python.exe" manage.py shell -c @"
from apps.users.models import User
print('yes' if User.objects.filter(email='$adminEmail').exists() else 'no')
"@) {
    Write-Host "[OK] Superuser $adminEmail already exists — password unchanged." -ForegroundColor Green
} else {
    $generated = [System.Web.Security.Membership]::GeneratePassword(20, 4, 4, 3, 0)
    $env:DJANGO_SUPERUSER_PASSWORD = $generated
    $env:DJANGO_SUPERUSER_EMAIL = $adminEmail
    & ".\venv\Scripts\python.exe" manage.py createsuperuser --noinput `
        --username $adminEmail --email $adminEmail 2>$null
    Remove-Item Env:\DJANGO_SUPERUSER_PASSWORD -ErrorAction SilentlyContinue
    Write-Host "[OK] Superuser created: $adminEmail" -ForegroundColor Green
    Write-Host "[!!] Generated password (shown once): $generated" -ForegroundColor Yellow
}

# 10. Collect static
Write-Host "`n[CARMA] Collecting static files..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" manage.py collectstatic --noinput | Out-Null

Write-Host "`n[CARMA] Setup complete." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Settings module: $settingsModule" -ForegroundColor White
Write-Host "  Start API:     .\venv\Scripts\python.exe manage.py runserver" -ForegroundColor White
Write-Host "  Start Daphne:  .\venv\Scripts\python.exe -m daphne -b 0.0.0.0 -p 8000 config.asgi:application" -ForegroundColor White
Write-Host "  Start Celery:  .\venv\Scripts\python.exe -m celery -A config worker --loglevel=info" -ForegroundColor White
Write-Host "  Django Admin:  http://localhost:8000/admin/" -ForegroundColor White
Write-Host "  API Docs:      http://localhost:8000/api/docs/" -ForegroundColor White
Write-Host "  Health:        http://localhost:8000/health/" -ForegroundColor White
Write-Host "  Platform:      http://localhost:8000/api/v1/system/status/" -ForegroundColor White
Write-Host ""
Write-Host "  Set DJANGO_SETTINGS_MODULE before running the server:" -ForegroundColor DarkGray
Write-Host "    `$env:DJANGO_SETTINGS_MODULE = '$settingsModule'" -ForegroundColor DarkGray
