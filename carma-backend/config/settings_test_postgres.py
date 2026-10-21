"""
CARMA — Test settings on PostgreSQL.

Same test configuration as ``config.settings_test`` (fast password hashing,
no throttling) but against a real PostgreSQL server, so the database-specific
behaviour — row locking in the audit chain, ``jsonb`` columns, ``uuid``
primary keys, unique-constraint handling — is exercised for real.

Point ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASSWORD`` at the running
server in ``.env``; the test database is created and dropped automatically.

    pytest --ds=config.settings_test_postgres
"""
from config.settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     config('DB_NAME', default='CARMADB'),  # noqa: F405
        'USER':     config('DB_USER', default='postgres'),  # noqa: F405
        'PASSWORD': config('DB_PASSWORD', default=''),  # noqa: F405
        'HOST':     config('DB_HOST', default='localhost'),  # noqa: F405
        'PORT':     config('DB_PORT', default='5432'),  # noqa: F405
        'OPTIONS': {
            'connect_timeout': 10,
            'options':         '-c search_path=public',
        },
        'CONN_MAX_AGE': 60,
        'TEST': {
            'NAME': config('DB_TEST_NAME', default='CARMADB_test'),  # noqa: F405
        },
    }
}

# Password hashing is the slowest part of the auth tests.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Throttling is disabled in tests: the rates are per-IP and would make the
# suite order-dependent (and fail on a shared machine).
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        'anon':  '1000/minute',
        'user':  '10000/minute',
        'login': '1000/minute',
    },
}

# No cache / broker side effects during tests.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
