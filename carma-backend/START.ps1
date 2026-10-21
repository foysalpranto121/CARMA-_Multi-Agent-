# ═══════════════════════════════════════════════════════════════
# CARMA Backend — Startup Commands (run these in PowerShell)
# ═══════════════════════════════════════════════════════════════

Set-Location -LiteralPath $PSScriptRoot

# Step 1 — Create the virtual environment (once)
python -m venv venv

# Step 2 — Install dependencies (once)
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# Step 3 — Copy the environment template (once)
if (-not (Test-Path ".\.env")) { Copy-Item ".\.env.example" ".\.env" }

# Step 4 — Choose the database
#
#   Quick start (no PostgreSQL, no Docker, no Redis):
#       $env:DJANGO_SETTINGS_MODULE = "config.settings_sqlite"
#
#   Research stack (PostgreSQL + Redis):
#       $env:DJANGO_SETTINGS_MODULE = "config.settings"
$env:DJANGO_SETTINGS_MODULE = "config.settings_sqlite"

# Step 5 — Migrate the database
.\venv\Scripts\python.exe manage.py migrate

# Step 6 — Seed the B0-B7 experiment configurations
.\venv\Scripts\python.exe manage.py seed_configurations

# Step 7 — Seed the S0-S6 benchmark scenarios
.\venv\Scripts\python.exe manage.py shell -c @"
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

# Step 8 — Create your own admin account (interactive, sets your own password)
.\venv\Scripts\python.exe manage.py createsuperuser

# Step 9 — Start the API
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000

# ─── URLs ──────────────────────────────────────────────────────
# Admin:       http://localhost:8000/admin/
# API Docs:    http://localhost:8000/api/docs/
# Health:      http://localhost:8000/health/
# API Base:    http://localhost:8000/api/v1/
# Platform:    http://localhost:8000/api/v1/system/status/
