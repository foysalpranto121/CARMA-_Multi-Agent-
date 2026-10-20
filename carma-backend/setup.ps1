#!/usr/bin/env pwsh
# ═══════════════════════════════════════════════════════════════
# CARMA Backend — Quick Setup Script (Windows PowerShell)
# ═══════════════════════════════════════════════════════════════

Write-Host "`n[CARMA] Starting backend setup..." -ForegroundColor Cyan

# 1. Check Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[ERROR] Python not found. Install Python 3.12+ first." -ForegroundColor Red; exit 1
}
Write-Host "[OK] Python: $(python --version)" -ForegroundColor Green

# 2. Create virtual environment
if (-not (Test-Path ".\venv")) {
    Write-Host "[CARMA] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}
Write-Host "[OK] Virtualenv ready." -ForegroundColor Green

# 3. Activate and install
Write-Host "[CARMA] Installing dependencies (this may take a few minutes)..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"
pip install --upgrade pip | Out-Null
pip install -r requirements.txt

# 4. Create .env if missing
if (-not (Test-Path ".\.env")) {
    Copy-Item ".\.env.example" ".\.env"
    Write-Host "[OK] .env created from template. Edit DB credentials if needed." -ForegroundColor Yellow
}

# 5. Create PostgreSQL database
Write-Host "`n[CARMA] Creating PostgreSQL database CARMADB..." -ForegroundColor Yellow
$env:PGPASSWORD = "pranto121"
$checkDb = psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='CARMADB'" 2>$null
if ($checkDb -notmatch "1") {
    psql -U postgres -c "CREATE DATABASE CARMADB;" 2>$null
    Write-Host "[OK] Database CARMADB created." -ForegroundColor Green
} else {
    Write-Host "[OK] Database CARMADB already exists." -ForegroundColor Green
}

# 6. Run Django migrations
Write-Host "`n[CARMA] Running migrations..." -ForegroundColor Yellow
python manage.py migrate

# 7. Create superuser
Write-Host "`n[CARMA] Creating admin superuser..." -ForegroundColor Yellow
python manage.py shell -c @"
from apps.users.models import User
if not User.objects.filter(email='admin@carma.ai').exists():
    User.objects.create_superuser(
        email='admin@carma.ai',
        password='carma123!',
        first_name='CARMA',
        last_name='Admin',
    )
    print('Superuser created: admin@carma.ai / carma123!')
else:
    print('Superuser already exists.')
"@

# 8. Load benchmark scenarios
Write-Host "`n[CARMA] Loading benchmark scenarios S0-S6..." -ForegroundColor Yellow
python manage.py shell -c @"
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
    print(f'  {code}: {name}')
print('Done.')
"@

# 9. Collect static
Write-Host "`n[CARMA] Collecting static files..." -ForegroundColor Yellow
python manage.py collectstatic --noinput | Out-Null

Write-Host "`n[CARMA] ✓ Setup complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Start API:     python manage.py runserver" -ForegroundColor White
Write-Host "  Start Daphne:  daphne -b 0.0.0.0 -p 8000 config.asgi:application" -ForegroundColor White
Write-Host "  Start Celery:  celery -A config worker --loglevel=info" -ForegroundColor White
Write-Host "  Django Admin:  http://localhost:8000/admin/" -ForegroundColor White
Write-Host "  API Docs:      http://localhost:8000/api/docs/" -ForegroundColor White
Write-Host "  Health:        http://localhost:8000/health/" -ForegroundColor White
Write-Host ""
Write-Host "  Demo credentials: admin@carma.ai / carma123!" -ForegroundColor Yellow
