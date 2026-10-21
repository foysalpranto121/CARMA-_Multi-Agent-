"""
CARMA — SQLite development settings.

Lets the whole stack run without PostgreSQL, Redis or Docker:

    export DJANGO_SETTINGS_MODULE=config.settings_sqlite
    python manage.py migrate
    python manage.py seed_configurations
    python manage.py runserver

Notes
-----
* SQLite has no ``select_for_update`` support, so the audit service skips the
  row lock there and relies on the unique ``sequence_num`` constraint plus a
  retry loop instead.
* Celery runs in eager mode, so experiment tasks execute inline.
* This module is for development and demos only — the research study runs on
  PostgreSQL (see ``config/settings.py``).
"""
from config.settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'carma.sqlite3',  # noqa: F405
        'OPTIONS': {'timeout': 20},
    }
}

# Password hashing is slow — use the fast hasher for local development.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Run Celery tasks inline (no Redis broker required).
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Local cache instead of Redis.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# In-memory channel layer (no Redis required for WebSockets).
CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
}

# The Vite dev server origin.
CORS_ALLOWED_ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']

# Auth is the last gate — do not redirect to HTTPS locally.
SECURE_SSL_REDIRECT = False
