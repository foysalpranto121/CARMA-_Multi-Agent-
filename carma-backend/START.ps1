# ═══════════════════════════════════════════════════════════════
# CARMA Backend — Startup Commands (run these in PowerShell)
# ═══════════════════════════════════════════════════════════════

# Step 1 — Navigate to backend
cd "d:\Thesis Paper\Code\carma-backend"

# Step 2 — Create virtual environment
python -m venv venv

# Step 3 — Activate venv
.\venv\Scripts\Activate.ps1

# Step 4 — Install core packages (minimal set to get server running)
pip install django==5.1.4 `
    djangorestframework==3.15.2 `
    djangorestframework-simplejwt==5.3.1 `
    django-cors-headers==4.6.0 `
    psycopg2-binary==2.9.10 `
    python-decouple==3.8 `
    drf-spectacular==0.27.2 `
    argon2-cffi==23.1.0 `
    django-filter==24.3 `
    channels==4.1.0 `
    daphne==4.1.2 `
    celery==5.4.0 `
    redis==5.2.0 `
    django-celery-results==2.5.1 `
    django-celery-beat==2.7.0

# Step 5 — Create PostgreSQL database (if not exists)
# Run in psql shell or pgAdmin:
# CREATE DATABASE "CARMADB";

# Step 6 — Run migrations
python manage.py migrate

# Step 7 — Create superuser (admin@carma.ai / carma123!)
python manage.py shell -c "
from apps.users.models import User
if not User.objects.filter(email='admin@carma.ai').exists():
    User.objects.create_superuser(email='admin@carma.ai', password='carma123!', first_name='CARMA', last_name='Admin')
    print('Superuser created OK')
else:
    print('Already exists')
"

# Step 8 — Seed benchmark scenarios S0-S6
python manage.py shell -c "
from apps.benchmark.models import BenchmarkScenario
data = [('S0','Nominal','No perturbation'),('S1','Exception','Unexpected event'),
        ('S2','Rule Change','Constraint changed mid-run'),('S3','Structural Drift','Model drift'),
        ('S4','Ambiguous Input','Underspecified input'),('S5','Conflicting Intents','Competing requests'),
        ('S6','Adversarial','Adversarial input')]
for code,name,desc in data:
    BenchmarkScenario.objects.get_or_create(code=code, defaults={'name':name,'description':desc})
print('Scenarios seeded OK')
"

# Step 9 — Start Django development server
python manage.py runserver 0.0.0.0:8000

# ─── URLs ──────────────────────────────────────────────────────
# Admin:       http://localhost:8000/admin/
# API Docs:    http://localhost:8000/api/docs/
# Health:      http://localhost:8000/health/
# API Base:    http://localhost:8000/api/v1/
